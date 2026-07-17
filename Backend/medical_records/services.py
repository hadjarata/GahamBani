from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import UserRole
from profiles.models import AssignmentStatus, PatientDoctorAssignment, PatientProfile
from profiles.selectors import doctor_can_access_patient

from .models import (
    Allergy,
    ChronicDisease,
    Consultation,
    DocumentUploadSource,
    MedicalDocument,
    MedicalNote,
    MedicalRecord,
    Treatment,
    TreatmentStatus,
)
from .validators import safe_original_filename, validate_uploaded_medical_document


def _lock_active_patient(patient_id):
    try:
        patient = PatientProfile.objects.select_for_update().select_related('user').get(
            pk=patient_id,
        )
    except PatientProfile.DoesNotExist as exc:
        raise ValidationError({'patient_id': 'The patient profile does not exist.'}) from exc
    if patient.user.role != UserRole.PATIENT or not patient.user.is_active:
        raise ValidationError({'patient_id': 'An active patient profile is required.'})
    return patient


def _lock_authorized_patient(actor, patient_id=None):
    if not actor.is_active:
        raise ValidationError('An active account is required.')
    if actor.role == UserRole.PATIENT:
        if not hasattr(actor, 'patient_profile'):
            raise ValidationError('The patient account has no patient profile.')
        if patient_id and str(patient_id) != str(actor.patient_profile.pk):
            raise ValidationError({'patient_id': 'Patients cannot select another owner.'})
        return _lock_active_patient(actor.patient_profile.pk)
    if actor.role != UserRole.DOCTOR or not hasattr(actor, 'doctor_profile'):
        raise ValidationError('A doctor or patient account is required.')
    if not patient_id:
        raise ValidationError({'patient_id': 'A patient is required for doctor operations.'})

    patient = _lock_active_patient(patient_id)
    if not doctor_can_access_patient(actor, patient.user):
        raise ValidationError({'patient_id': 'The doctor is not assigned to this patient.'})
    assignment_exists = PatientDoctorAssignment.objects.select_for_update().filter(
        doctor=actor.doctor_profile,
        patient=patient,
        status=AssignmentStatus.ACTIVE,
        ended_at__isnull=True,
    ).exists()
    if not assignment_exists:
        raise ValidationError({'patient_id': 'The doctor is not assigned to this patient.'})
    return patient


def _validate_and_save(instance):
    instance.full_clean()
    instance.save()
    return instance


@transaction.atomic
def create_medical_record(*, patient):
    patient = _lock_active_patient(patient.pk)
    try:
        return MedicalRecord.objects.select_for_update().get(patient=patient)
    except MedicalRecord.DoesNotExist:
        record = MedicalRecord(patient=patient)
        record.full_clean()
        try:
            with transaction.atomic():
                record.save(force_insert=True)
        except IntegrityError:
            return MedicalRecord.objects.select_for_update().get(patient=patient)
        return record


def _authorized_record(actor, patient_id):
    patient = _lock_authorized_patient(actor, patient_id)
    return create_medical_record(patient=patient)


@transaction.atomic
def add_chronic_disease(*, doctor, patient_id, data):
    record = _authorized_record(doctor, patient_id)
    return _validate_and_save(ChronicDisease(medical_record=record, **data))


@transaction.atomic
def add_allergy(*, doctor, patient_id, data):
    record = _authorized_record(doctor, patient_id)
    return _validate_and_save(Allergy(medical_record=record, **data))


@transaction.atomic
def create_treatment(*, doctor, patient_id, data):
    record = _authorized_record(doctor, patient_id)
    return _validate_and_save(Treatment(
        medical_record=record,
        prescrit_par=doctor,
        **data,
    ))


@transaction.atomic
def stop_treatment(treatment, *, doctor, end_date=None):
    locked = Treatment.objects.select_for_update().select_related(
        'medical_record__patient__user',
    ).get(pk=treatment.pk)
    if not doctor_can_access_patient(doctor, locked.medical_record.patient.user):
        raise ValidationError('The doctor is not currently assigned to this patient.')
    locked.statut = TreatmentStatus.STOPPED
    locked.date_fin = end_date or timezone.localdate()
    return _validate_and_save(locked)


@transaction.atomic
def create_consultation(*, doctor, patient_id, data):
    patient = _lock_authorized_patient(doctor, patient_id)
    return _validate_and_save(Consultation(
        patient=patient,
        medecin=doctor.doctor_profile,
        **data,
    ))


@transaction.atomic
def create_medical_note(*, doctor, patient_id, data):
    record = _authorized_record(doctor, patient_id)
    return _validate_and_save(MedicalNote(
        medical_record=record,
        auteur=doctor,
        **data,
    ))


@transaction.atomic
def update_clinical_object(instance, *, doctor, data, immutable_fields=()):
    model_class = type(instance)
    locked = model_class.objects.select_for_update().select_related(
        *clinical_select_related(model_class),
    ).get(pk=instance.pk)
    patient_user = patient_user_for_object(locked)
    if not doctor_can_access_patient(doctor, patient_user):
        raise ValidationError('The doctor is not currently assigned to this patient.')
    if isinstance(locked, MedicalNote) and locked.auteur_id != doctor.pk:
        raise ValidationError('Only the note author may modify this medical note.')
    for field, value in data.items():
        if field not in immutable_fields:
            setattr(locked, field, value)
    return _validate_and_save(locked)


@transaction.atomic
def upload_medical_document(*, actor, patient_id, data):
    patient = _lock_authorized_patient(actor, patient_id)
    record = create_medical_record(patient=patient)
    uploaded_file = data.pop('fichier')
    validate_uploaded_medical_document(uploaded_file)
    source = (
        DocumentUploadSource.PATIENT
        if actor.role == UserRole.PATIENT
        else DocumentUploadSource.DOCTOR
    )
    document = MedicalDocument(
        medical_record=record,
        uploaded_by=actor,
        fichier=uploaded_file,
        original_filename=safe_original_filename(uploaded_file.name),
        mime_type=uploaded_file.content_type,
        file_size=uploaded_file.size,
        upload_source=source,
        **data,
    )
    document.full_clean()
    try:
        document.save(force_insert=True)
    except Exception:
        if document.fichier.name and document.fichier.storage.exists(document.fichier.name):
            document.fichier.storage.delete(document.fichier.name)
        raise
    return document


def patient_user_for_object(obj):
    if isinstance(obj, Consultation):
        return obj.patient.user
    if isinstance(obj, MedicalRecord):
        return obj.patient.user
    return obj.medical_record.patient.user


def clinical_select_related(model_class):
    if model_class is Consultation:
        return ('patient__user', 'medecin__user')
    return ('medical_record__patient__user',)
