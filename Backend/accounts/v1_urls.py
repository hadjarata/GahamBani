from django.urls import path

from .views import (
    ChangePasswordView,
    DocumentedTokenRefreshView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetView,
    RegisterV1View,
)


urlpatterns = [
    path('register/', RegisterV1View.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('refresh/', DocumentedTokenRefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='me'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('password-reset/', PasswordResetView.as_view(), name='password_reset'),
    path(
        'password-reset-confirm/',
        PasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
]
