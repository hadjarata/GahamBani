from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from accounts.models import UserRole
from profiles.models import PatientProfile

from .models import BloodGlucose, BloodPressure, MeasurementSource


def _get_locked_active_patient(patient):
    try:
        locked = PatientProfile.objects.select_for_update().select_related('user').get(
            pk=patient.pk,
        )
    except PatientProfile.DoesNotExist as exc:
        raise DjangoValidationError({'patient': 'The patient profile does not exist.'}) from exc
    if locked.user.role != UserRole.PATIENT or not locked.user.is_active:
        raise DjangoValidationError({'patient': 'An active patient profile is required.'})
    return locked


@transaction.atomic
def create_measurement(model_class, *, patient, validated_data):
    """Create a patient-entered measurement without triggering alerts."""
    if model_class not in (BloodPressure, BloodGlucose):
        raise ValueError('Unsupported monitoring measurement model.')
    patient = _get_locked_active_patient(patient)
    measurement = model_class(
        patient=patient,
        source_mesure=MeasurementSource.MANUAL,
        **validated_data,
    )
    measurement.full_clean()
    measurement.save(force_insert=True)
    return measurement


@transaction.atomic
def update_measurement(measurement, *, patient_user, validated_data):
    """Update an owned measurement while preserving owner and source."""
    model_class = type(measurement)
    locked = model_class.objects.select_for_update().select_related('patient__user').get(
        pk=measurement.pk,
    )
    if locked.patient.user_id != patient_user.pk or not patient_user.is_active:
        raise DjangoValidationError('Only the active patient owner may update this measurement.')
    for field, value in validated_data.items():
        if field not in {'patient', 'source_mesure'}:
            setattr(locked, field, value)
    locked.full_clean()
    locked.save()
    return locked
