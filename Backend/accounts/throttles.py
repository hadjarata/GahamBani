from rest_framework.settings import api_settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class ConfigurableThrottleRateMixin:
    """Read rates at instantiation time so Django setting overrides are honored."""

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)


class ConfigurableAnonRateThrottle(ConfigurableThrottleRateMixin, AnonRateThrottle):
    pass


class ConfigurableUserRateThrottle(ConfigurableThrottleRateMixin, UserRateThrottle):
    pass


class PublicEndpointRateThrottle(ConfigurableAnonRateThrottle):
    """Throttle a public operation by client IP, even with a JWT attached.

    Standard ``AnonRateThrottle`` skips authenticated requests. Public account
    operations do not become less sensitive when a caller supplies a valid
    token, so their dedicated scope must remain effective in that case.
    """

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident,
        }


class RegistrationRateThrottle(PublicEndpointRateThrottle):
    scope = 'registration'


class LoginRateThrottle(PublicEndpointRateThrottle):
    scope = 'login'


class PasswordResetRateThrottle(PublicEndpointRateThrottle):
    scope = 'password_reset'


class PasswordResetConfirmRateThrottle(PublicEndpointRateThrottle):
    scope = 'password_reset_confirm'


class TokenRefreshRateThrottle(PublicEndpointRateThrottle):
    scope = 'token_refresh'


class PublicEndpointThrottleMixin:
    """Add an endpoint scope while preserving DRF's global throttles."""

    endpoint_throttle_class = None

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.endpoint_throttle_class is not None:
            throttles.append(self.endpoint_throttle_class())
        return throttles
