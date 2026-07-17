from rest_framework.permissions import BasePermission

from accounts.models import UserRole


class ActiveProfileAPIPermission(BasePermission):
    message = 'Un compte patient ou médecin actif est requis.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and user.is_active
            and user.role in (UserRole.PATIENT, UserRole.DOCTOR)
        )


class DoctorEndpointPermission(ActiveProfileAPIPermission):
    message = 'Cet endpoint est réservé aux médecins actifs.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == UserRole.DOCTOR


class PatientEndpointPermission(ActiveProfileAPIPermission):
    message = 'Cet endpoint est réservé aux patients actifs.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == UserRole.PATIENT
