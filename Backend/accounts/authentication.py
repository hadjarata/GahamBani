from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from .tokens import token_version_matches


INVALID_TOKEN_MESSAGE = 'Token is invalid or expired.'


class VersionedJWTAuthentication(JWTAuthentication):
    """Reject access tokens issued for an older user token version."""

    def get_user(self, validated_token):
        try:
            user = super().get_user(validated_token)
        except AuthenticationFailed as exc:
            raise AuthenticationFailed(
                INVALID_TOKEN_MESSAGE,
                code='token_not_valid',
            ) from exc
        if not token_version_matches(validated_token, user):
            raise AuthenticationFailed(
                INVALID_TOKEN_MESSAGE,
                code='token_not_valid',
            )
        return user


class VersionedJWTScheme(SimpleJWTScheme):
    """Document the custom authenticator as the existing JWT bearer scheme."""

    target_class = VersionedJWTAuthentication
