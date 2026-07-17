from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import UserRole
from alerts.models import MedicalAlert
from monitoring.models import BloodGlucose, BloodPressure
from profiles.models import PatientProfile
from profiles.selectors import doctor_can_access_patient


def resolve_authorized_patient(*, user, patient_id=None):
    """Resolve the sole patient an analytics request may address."""
    if user.role == UserRole.PATIENT:
        if patient_id:
            raise ValidationError({'patient_id': 'Un patient ne peut pas choisir un autre dossier.'})
        try:
            return PatientProfile.objects.select_related('user').get(
                user=user, user__is_active=True, user__role=UserRole.PATIENT,
            )
        except PatientProfile.DoesNotExist as exc:
            raise PermissionDenied('Un profil patient actif est requis.') from exc

    if user.role != UserRole.DOCTOR:
        raise PermissionDenied('Ce rôle ne donne pas accès aux données médicales.')
    if not hasattr(user, 'doctor_profile'):
        raise PermissionDenied('Un profil médecin actif est requis.')
    if not patient_id:
        raise ValidationError({'patient_id': 'Ce paramètre est obligatoire pour un médecin.'})
    try:
        patient = PatientProfile.objects.select_related('user').get(
            pk=patient_id, user__is_active=True, user__role=UserRole.PATIENT,
        )
    except PatientProfile.DoesNotExist as exc:
        raise NotFound('Patient inaccessible.') from exc
    if not doctor_can_access_patient(user, patient.user):
        raise NotFound('Patient inaccessible.')
    return patient


def blood_pressure_queryset(*, patient, date_from, date_to):
    return BloodPressure.objects.filter(
        patient=patient, date_mesure__gte=date_from, date_mesure__lte=date_to,
    )


def blood_glucose_queryset(*, patient, date_from, date_to, context=None):
    queryset = BloodGlucose.objects.filter(
        patient=patient, date_mesure__gte=date_from, date_mesure__lte=date_to,
    )
    return queryset.filter(contexte_repas=context) if context else queryset


def alert_queryset(*, patient, date_from, date_to):
    return MedicalAlert.objects.filter(
        patient=patient, detected_at__gte=date_from, detected_at__lte=date_to,
    )
