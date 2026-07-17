from rest_framework.permissions import BasePermission

from accounts.models import UserRole


class AnalyticsPermission(BasePermission):
    message = 'Un compte patient ou médecin actif est requis.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.role in (UserRole.PATIENT, UserRole.DOCTOR)
        )

