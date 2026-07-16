from rest_framework import status
from rest_framework.generics import CreateAPIView, GenericAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    LoginUserSerializer,
    LogoutSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    PublicUserSerializer,
    RegisterSerializer,
)


class RegisterView(CreateAPIView):
    """Register a patient account without issuing authentication tokens."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        headers = self.get_success_headers(PublicUserSerializer(user).data)
        return Response(
            {
                'message': 'Account created successfully.',
                'user': PublicUserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class LoginView(GenericAPIView):
    """Authenticate a user by email and issue a JWT token pair."""

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                'message': 'Login successful.',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': LoginUserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class MeView(RetrieveUpdateAPIView):
    """Retrieve or update the authenticated user's permitted profile fields."""

    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_object(self):
        return self.request.user


class LogoutView(GenericAPIView):
    """Blacklist the authenticated user's submitted refresh token."""

    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({'message': 'Logout successful.'}, status=status.HTTP_200_OK)


class ChangePasswordView(GenericAPIView):
    """Change the authenticated user's password after validating the old one."""

    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Password changed successfully.'},
            status=status.HTTP_200_OK,
        )


class PasswordResetView(GenericAPIView):
    """Generate password-reset credentials for an active account."""

    serializer_class = PasswordResetSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=status.HTTP_200_OK)


class PasswordResetConfirmView(GenericAPIView):
    """Set a new password using valid Django reset credentials."""

    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Password reset successful.'},
            status=status.HTTP_200_OK,
        )
