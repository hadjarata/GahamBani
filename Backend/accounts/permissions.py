from rest_framework.permissions import BasePermission

from .models import UserRole


class RolePermission(BasePermission):
    """Base permission for role-based access checks on authenticated users."""

    allowed_roles = ()

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return bool(
            user
            and user.is_authenticated
            and user.role in self.allowed_roles
        )


class IsPatient(RolePermission):
    allowed_roles = (UserRole.PATIENT,)


class IsDoctor(RolePermission):
    allowed_roles = (UserRole.DOCTOR,)


class IsAdmin(RolePermission):
    allowed_roles = (UserRole.ADMIN,)


class IsDoctorOrAdmin(RolePermission):
    allowed_roles = (UserRole.DOCTOR, UserRole.ADMIN)


class IsOwner(BasePermission):
    """Allow access only to an authenticated user owning the target object.

    A view can configure ``owner_field`` (single string) or ``owner_fields``
    (iterable). Nested paths such as ``patient__user`` are supported.
    """

    owner_fields = ('owner', 'user', 'patient')

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        for field_path in self.get_owner_fields(view):
            owner = self.resolve_owner(obj, field_path)
            if owner == user or getattr(owner, 'user', None) == user:
                return True
        return False

    def get_owner_fields(self, view):
        fields = getattr(view, 'owner_fields', None)
        if fields is None:
            fields = getattr(view, 'owner_field', self.owner_fields)
        return (fields,) if isinstance(fields, str) else tuple(fields)

    @staticmethod
    def resolve_owner(obj, field_path):
        value = obj
        for field_name in field_path.replace('.', '__').split('__'):
            value = getattr(value, field_name, None)
            if value is None:
                return None
        return value
