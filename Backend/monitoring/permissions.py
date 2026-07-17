from rest_framework.permissions import BasePermission, SAFE_METHODS

from accounts.models import UserRole
from profiles.selectors import doctor_can_access_patient


class MonitoringMeasurementPermission(BasePermission):
    """Patients own writes; currently assigned doctors have read-only access."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.role == UserRole.PATIENT:
            if request.method == 'POST':
                return hasattr(user, 'patient_profile')
            # PUT/DELETE pass initial permission checking so DRF can return the
            # documented 405 from the viewset's disabled HTTP methods.
            return request.method in SAFE_METHODS or request.method in ('PATCH', 'PUT', 'DELETE')
        if user.role == UserRole.DOCTOR:
            return request.method in SAFE_METHODS
        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        patient_user = obj.patient.user
        if user.role == UserRole.PATIENT:
            return (
                user.is_active
                and patient_user.is_active
                and user.pk == patient_user.pk
                and (request.method in SAFE_METHODS or request.method == 'PATCH')
            )
        if user.role == UserRole.DOCTOR and request.method in SAFE_METHODS:
            return doctor_can_access_patient(user, patient_user)
        return False
