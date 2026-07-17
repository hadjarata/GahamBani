from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import UserRole


class NotificationPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.role not in (UserRole.PATIENT, UserRole.DOCTOR):
            return False
        return request.method in SAFE_METHODS or request.method in ('PATCH', 'PUT', 'DELETE', 'POST')

    def has_object_permission(self, request, view, obj):
        return obj.recipient_id == request.user.pk
