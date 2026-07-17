from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import UserRole
from profiles.selectors import doctor_can_access_patient


class AlertPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.role == UserRole.PATIENT:
            return request.method in SAFE_METHODS or request.method in ('PUT', 'DELETE')
        if user.role == UserRole.DOCTOR:
            return request.method in SAFE_METHODS or request.method in ('PATCH', 'PUT', 'DELETE')
        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role == UserRole.PATIENT:
            return request.method in SAFE_METHODS and obj.patient.user_id == user.pk
        if user.role == UserRole.DOCTOR:
            return doctor_can_access_patient(user, obj.patient.user)
        return False
