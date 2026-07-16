from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, UserRole


password_reset_token_generator = PasswordResetTokenGenerator()


def validate_user_password(password, user):
    """Run Django's configured password validators and expose DRF errors."""
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc


class PublicUserSerializer(serializers.ModelSerializer):
    """Expose only the user data safe to return from public endpoints."""

    class Meta:
        model = User
        fields = (
            'id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'role',
            'is_verified',
            'created_at',
        )
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'email',
            'phone',
            'password',
            'password_confirm',
        )
        extra_kwargs = {
            'first_name': {'required': True, 'allow_blank': False},
            'last_name': {'required': True, 'allow_blank': False},
            'phone': {'required': True, 'allow_blank': False},
        }

    def validate_email(self, value):
        email = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return email

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'The two password fields did not match.',
            })

        user = User(
            email=attrs['email'],
            first_name=attrs['first_name'],
            last_name=attrs['last_name'],
            phone=attrs['phone'],
        )
        validate_password(attrs['password'], user=user)
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')

        with transaction.atomic():
            return User.objects.create_user(
                password=password,
                role=UserRole.PATIENT,
                is_active=True,
                is_verified=False,
                **validated_data,
            )


class LoginUserSerializer(serializers.ModelSerializer):
    """Expose the public user fields returned after a successful login."""

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email', 'role')
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    default_error_messages = {
        'invalid_credentials': 'Unable to log in with the provided credentials.',
    }

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get('request'),
            email=attrs['email'],
            password=attrs['password'],
        )

        if user is None:
            self.fail('invalid_credentials')

        attrs['user'] = user
        return attrs


class MeSerializer(serializers.ModelSerializer):
    """Serialize the authenticated user and limit editable profile fields."""

    editable_fields = {'first_name', 'last_name', 'phone'}

    class Meta:
        model = User
        fields = (
            'id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'role',
            'is_verified',
            'created_at',
        )
        read_only_fields = (
            'id',
            'email',
            'role',
            'is_verified',
            'created_at',
        )

    def validate(self, attrs):
        forbidden_fields = set(self.initial_data) - self.editable_fields
        if forbidden_fields:
            raise serializers.ValidationError({
                field: 'This field cannot be modified.'
                for field in forbidden_fields
            })
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True, trim_whitespace=False)

    default_error_messages = {
        'invalid_token': 'The refresh token is invalid or has expired.',
        'wrong_user': 'The refresh token does not belong to the authenticated user.',
    }

    def validate(self, attrs):
        try:
            refresh_token = RefreshToken(attrs['refresh'])
        except TokenError:
            self.fail('invalid_token')

        request = self.context['request']
        if str(refresh_token.get('user_id')) != str(request.user.pk):
            self.fail('wrong_user')

        attrs['refresh_token'] = refresh_token
        return attrs

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                self.validated_data['refresh_token'].blacklist()
        except TokenError:
            self.fail('invalid_token')


class ChangePasswordSerializer(serializers.Serializer):
    """Validate and change the authenticated user's password."""

    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_old_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('The old password is incorrect.')
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': 'The two password fields did not match.',
            })

        try:
            validate_user_password(
                attrs['new_password'],
                self.context['request'].user,
            )
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({'new_password': exc.detail}) from exc
        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        with transaction.atomic():
            user.set_password(self.validated_data['new_password'])
            user.save(update_fields=('password', 'updated_at'))
        return user


class PasswordResetSerializer(serializers.Serializer):
    """Generate a Django password-reset token without sending an email."""

    email = serializers.EmailField(write_only=True)

    def validate_email(self, value):
        self.user = User.objects.filter(
            email__iexact=User.objects.normalize_email(value),
            is_active=True,
        ).first()
        return value

    def save(self, **kwargs):
        if self.user is None:
            return {
                'message': 'If the account exists, a reset link has been generated.',
            }

        return {
            'message': 'Password reset link generated.',
            'uid': urlsafe_base64_encode(force_bytes(self.user.pk)),
            'token': password_reset_token_generator.make_token(self.user),
        }


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Validate a Django reset token and set the user's new password."""

    uid = serializers.CharField(write_only=True)
    token = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    default_error_messages = {
        'invalid_link': 'The password reset link is invalid or has expired.',
    }

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': 'The two password fields did not match.',
            })

        try:
            user_id = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=user_id, is_active=True)
        except (
            TypeError,
            ValueError,
            OverflowError,
            UnicodeDecodeError,
            User.DoesNotExist,
        ):
            self.fail('invalid_link')

        if not password_reset_token_generator.check_token(user, attrs['token']):
            self.fail('invalid_link')

        try:
            validate_user_password(attrs['new_password'], user)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({'new_password': exc.detail}) from exc

        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data['user']
        with transaction.atomic():
            user.set_password(self.validated_data['new_password'])
            user.save(update_fields=('password', 'updated_at'))
        return user
