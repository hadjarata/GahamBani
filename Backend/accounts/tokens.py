from rest_framework_simplejwt.tokens import RefreshToken


TOKEN_VERSION_CLAIM = 'token_version'


def token_version_matches(token, user):
    """Return True only for an integer claim matching the current user state."""
    claimed_version = token.get(TOKEN_VERSION_CLAIM)
    return type(claimed_version) is int and claimed_version == user.token_version


class VersionedRefreshToken(RefreshToken):
    """Issue refresh/access pairs bound to the user's current token version."""

    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token[TOKEN_VERSION_CLAIM] = user.token_version
        return token
