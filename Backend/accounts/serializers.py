from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .authentication import INVALID_TOKEN_MESSAGE
from .models import User, UserRole
from .services import (
    register_patient,
    send_password_reset_email,
    set_user_password_and_revoke_tokens,
)
from .tokens import VersionedRefreshToken, token_version_matches


PASSWORD_RESET_RESPONSE = {
    'detail': 'Si un compte correspondant existe, un lien de réinitialisation a été envoyé.',
}


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
    public_fields = {
        'first_name',
        'last_name',
        'email',
        'phone',
        'password',
        'password_confirm',
    }
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
            # The service owns uniqueness so v1 can return a race-safe 409.
            'email': {'validators': []},
        }

    def validate_email(self, value):
        email = User.objects.normalize_email(value).strip().lower()
        request = self.context.get('request')
        is_v1 = request is not None and request.path.startswith('/api/v1/')
        if not is_v1 and User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return email

    def validate(self, attrs):
        forbidden_fields = set(self.initial_data) - self.public_fields
        if forbidden_fields:
            raise serializers.ValidationError({
                field: 'Ce champ n’est pas autorisé à l’inscription publique.'
                for field in sorted(forbidden_fields)
            })

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
        user, self.patient_profile = register_patient(
            password=password,
            **validated_data,
        )
        return user


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
        return set_user_password_and_revoke_tokens(
            user,
            self.validated_data['new_password'],
        )


class PasswordResetSerializer(serializers.Serializer):
    """Send reset credentials by email without revealing account existence."""

    email = serializers.EmailField(write_only=True)

    def validate_email(self, value):
        self.user = User.objects.filter(
            email__iexact=User.objects.normalize_email(value),
            is_active=True,
        ).first()
        return value

    def save(self, **kwargs):
        if self.user is not None:
            send_password_reset_email(self.user)
        return PASSWORD_RESET_RESPONSE.copy()


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

        if not default_token_generator.check_token(user, attrs['token']):
            self.fail('invalid_link')

        try:
            validate_user_password(attrs['new_password'], user)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({'new_password': exc.detail}) from exc

        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data['user']
        return set_user_password_and_revoke_tokens(
            user,
            self.validated_data['new_password'],
        )


class VersionedTokenRefreshSerializer(TokenRefreshSerializer):
    """Reject refresh tokens issued for an older user token version."""

    token_class = VersionedRefreshToken

    def validate(self, attrs):
        refresh = self.token_class(attrs['refresh'])
        user_id = refresh.get(api_settings.USER_ID_CLAIM)

        try:
            with transaction.atomic():
                user = get_user_model().objects.select_for_update().get(
                    **{api_settings.USER_ID_FIELD: user_id},
                )
                if not user.is_active or not token_version_matches(refresh, user):
                    raise AuthenticationFailed(
                        INVALID_TOKEN_MESSAGE,
                        code='token_not_valid',
                    )
                # The row lock prevents a concurrent password change between
                # the version check and token rotation/issuance.
                return super().validate(attrs)
        except get_user_model().DoesNotExist as exc:
            raise AuthenticationFailed(
                INVALID_TOKEN_MESSAGE,
                code='token_not_valid',
            ) from exc


# Response serializers make the generated OpenAPI contract match the custom
# response envelopes returned by the authentication views.
class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField(read_only=True)


class RegisterResponseSerializer(MessageResponseSerializer):
    user = PublicUserSerializer(read_only=True)


class RegistrationUserSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    role = serializers.ChoiceField(choices=UserRole.choices, read_only=True)


class RegistrationProfileSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    profile_type = serializers.CharField(read_only=True)


class RegistrationOnboardingSerializer(serializers.Serializer):
    is_complete = serializers.BooleanField(read_only=True)
    completion_percentage = serializers.IntegerField(read_only=True)
    missing_fields = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
    )


class RegisterV1ResponseSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)
    user = RegistrationUserSerializer(read_only=True)
    profile = RegistrationProfileSerializer(read_only=True)
    onboarding = RegistrationOnboardingSerializer(read_only=True)


class LoginResponseSerializer(MessageResponseSerializer):
    refresh = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)
    user = LoginUserSerializer(read_only=True)


class PasswordResetResponseSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)


class TokenRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True, required=False)
