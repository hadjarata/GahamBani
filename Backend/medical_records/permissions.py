from rest_framework.permissions import SAFE_METHODS, BasePermission
from uuid import UUID

from accounts.models import UserRole
from profiles.models import PatientProfile
from profiles.selectors import doctor_can_access_patient

from .services import patient_user_for_object


class MedicalRecordPermission(BasePermission):
    """Deny administrators; patients own reads/uploads; assigned doctors clinical access."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.role == UserRole.PATIENT:
            if request.method == 'POST':
                return bool(getattr(view, 'patient_upload_allowed', False)) and hasattr(
                    user, 'patient_profile',
                )
            return request.method in SAFE_METHODS or request.method in ('PUT', 'DELETE')
        if user.role == UserRole.DOCTOR:
            if request.method == 'POST':
                patient_id = request.data.get('patient_id')
                if patient_id:
                    try:
                        patient_id = UUID(str(patient_id))
                    except (TypeError, ValueError):
                        return True  # The serializer returns the precise 400 response.
                    patient_user = PatientProfile.objects.filter(
                        pk=patient_id,
                    ).select_related('user').first()
                    return bool(
                        patient_user
                        and doctor_can_access_patient(user, patient_user.user)
                    )
            return request.method in SAFE_METHODS or request.method in (
                'POST', 'PATCH', 'PUT', 'DELETE',
            )
        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        patient_user = patient_user_for_object(obj)
        if user.role == UserRole.PATIENT:
            return (
                user.pk == patient_user.pk
                and patient_user.is_active
                and request.method in SAFE_METHODS
            )
        if user.role == UserRole.DOCTOR:
            return doctor_can_access_patient(user, patient_user)
        return False
