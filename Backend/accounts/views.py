from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import CreateAPIView, GenericAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView

from .models import UserRole
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    LoginUserSerializer,
    LoginResponseSerializer,
    LogoutSerializer,
    MeSerializer,
    MessageResponseSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetResponseSerializer,
    PasswordResetSerializer,
    PublicUserSerializer,
    RegisterResponseSerializer,
    RegisterSerializer,
    RegisterV1ResponseSerializer,
    TokenRefreshResponseSerializer,
    VersionedTokenRefreshSerializer,
)
from .throttles import (
    LoginRateThrottle,
    PasswordResetConfirmRateThrottle,
    PasswordResetRateThrottle,
    PublicEndpointThrottleMixin,
    RegistrationRateThrottle,
    TokenRefreshRateThrottle,
)
from .tokens import VersionedRefreshToken
from profiles.services import get_profile_completion


BAD_REQUEST = OpenApiResponse(description='Requête invalide ou erreur de validation.')
UNAUTHORIZED = OpenApiResponse(description='Authentification JWT requise ou invalide.')
TOO_MANY_REQUESTS = OpenApiResponse(
    description='Limite de requêtes dépassée. Le délai est indiqué par DRF lorsque disponible.',
)
CONFLICT = OpenApiResponse(description='Cette adresse e-mail est déjà utilisée.')
PROFILE_CREATION_ERROR = OpenApiResponse(
    description='Le compte et le profil ont été annulés car le profil n’a pas pu être créé.',
)


@extend_schema_view(
    post=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_register',
        summary='Créer un compte patient',
        description=(
            'Crée un compte patient actif et non vérifié. Aucun jeton JWT '
            'n’est émis lors de l’inscription.'
        ),
        request=RegisterSerializer,
        responses={201: RegisterResponseSerializer, 400: BAD_REQUEST, 429: TOO_MANY_REQUESTS},
        auth=[],
    ),
)
class RegisterView(PublicEndpointThrottleMixin, CreateAPIView):
    """Register a patient account without issuing authentication tokens."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    endpoint_throttle_class = RegistrationRateThrottle

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


@extend_schema_view(
    post=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_register',
        summary='Créer un compte patient et son profil',
        description=(
            'Crée atomiquement un compte PATIENT actif et non vérifié ainsi '
            'qu’un profil patient incomplet. Aucun jeton JWT n’est émis.'
        ),
        request=RegisterSerializer,
        responses={
            201: RegisterV1ResponseSerializer,
            400: BAD_REQUEST,
            409: CONFLICT,
            429: TOO_MANY_REQUESTS,
            500: PROFILE_CREATION_ERROR,
        },
        auth=[],
    ),
)
class RegisterV1View(RegisterView):
    """Expose the stable v1 registration and onboarding contract."""

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        profile = serializer.patient_profile
        return Response(
            {
                'detail': 'Compte patient créé avec succès.',
                'user': {
                    'id': str(user.pk),
                    'email': user.email,
                    'role': user.role,
                },
                'profile': {
                    'id': str(profile.pk),
                    'profile_type': UserRole.PATIENT,
                },
                'onboarding': get_profile_completion(user, profile),
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    post=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_login',
        summary='Se connecter',
        description='Authentifie un utilisateur par e-mail et retourne une paire de jetons JWT.',
        request=LoginSerializer,
        responses={200: LoginResponseSerializer, 400: BAD_REQUEST, 429: TOO_MANY_REQUESTS},
        auth=[],
    ),
)
class LoginView(PublicEndpointThrottleMixin, GenericAPIView):
    """Authenticate a user by email and issue a JWT token pair."""

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    endpoint_throttle_class = LoginRateThrottle

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = VersionedRefreshToken.for_user(user)

        return Response(
            {
                'message': 'Login successful.',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': LoginUserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_me_retrieve',
        summary='Consulter son compte',
        responses={200: MeSerializer, 401: UNAUTHORIZED, 429: TOO_MANY_REQUESTS},
    ),
    patch=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_me_update',
        summary='Modifier son compte',
        description='Modifie uniquement le prénom, le nom et le numéro de téléphone.',
        request=MeSerializer,
        responses={
            200: MeSerializer,
            400: BAD_REQUEST,
            401: UNAUTHORIZED,
            429: TOO_MANY_REQUESTS,
        },
    ),
)
class MeView(RetrieveUpdateAPIView):
    """Retrieve or update the authenticated user's permitted profile fields."""

    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_object(self):
        return self.request.user


@extend_schema_view(
    post=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_logout',
        summary='Se déconnecter',
        description='Place le jeton de rafraîchissement fourni sur la liste noire.',
        request=LogoutSerializer,
        responses={
            200: MessageResponseSerializer,
            400: BAD_REQUEST,
            401: UNAUTHORIZED,
            429: TOO_MANY_REQUESTS,
        },
    ),
)
class LogoutView(GenericAPIView):
    """Blacklist the authenticated user's submitted refresh token."""

    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({'message': 'Logout successful.'}, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_change_password',
        summary='Changer son mot de passe',
        request=ChangePasswordSerializer,
        responses={
            200: MessageResponseSerializer,
            400: BAD_REQUEST,
            401: UNAUTHORIZED,
            429: TOO_MANY_REQUESTS,
        },
    ),
)
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


@extend_schema_view(
    post=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_password_reset',
        summary='Demander une réinitialisation du mot de passe',
        description=(
            'Envoie un lien de réinitialisation par e-mail si un compte actif existe. '
            'La réponse reste identique quel que soit le compte demandé.'
        ),
        request=PasswordResetSerializer,
        responses={
            200: PasswordResetResponseSerializer,
            400: BAD_REQUEST,
            429: TOO_MANY_REQUESTS,
        },
        auth=[],
    ),
)
class PasswordResetView(PublicEndpointThrottleMixin, GenericAPIView):
    """Email reset credentials without revealing whether an account exists."""

    serializer_class = PasswordResetSerializer
    permission_classes = [AllowAny]
    endpoint_throttle_class = PasswordResetRateThrottle

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_password_reset_confirm',
        summary='Confirmer la réinitialisation du mot de passe',
        request=PasswordResetConfirmSerializer,
        responses={200: MessageResponseSerializer, 400: BAD_REQUEST, 429: TOO_MANY_REQUESTS},
        auth=[],
    ),
)
class PasswordResetConfirmView(PublicEndpointThrottleMixin, GenericAPIView):
    """Set a new password using valid Django reset credentials."""

    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]
    endpoint_throttle_class = PasswordResetConfirmRateThrottle

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Password reset successful.'},
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
        tags=['Domaine 1 - Authentification'],
        operation_id='auth_token_refresh',
        summary='Rafraîchir un jeton JWT',
        description='Retourne un nouveau jeton d’accès à partir d’un jeton de rafraîchissement.',
        responses={
            200: TokenRefreshResponseSerializer,
            401: UNAUTHORIZED,
            429: TOO_MANY_REQUESTS,
        },
        auth=[],
    ),
)
class DocumentedTokenRefreshView(PublicEndpointThrottleMixin, TokenRefreshView):
    """Token refresh endpoint documented as part of Domaine 1."""

    endpoint_throttle_class = TokenRefreshRateThrottle
    serializer_class = VersionedTokenRefreshSerializer
