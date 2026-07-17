from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User, UserRole

from .models import AssignmentStatus, DoctorProfile, PatientDoctorAssignment, PatientProfile


PROFILE_REQUIRED_FIELDS = {
    UserRole.PATIENT: ('first_name', 'last_name', 'phone', 'date_naissance', 'sexe', 'poids', 'taille'),
    UserRole.DOCTOR: ('first_name', 'last_name', 'phone', 'specialite', 'numero_ordre', 'hopital', 'annees_experience'),
}


def get_profile_for_user(user):
    if user.role == UserRole.PATIENT:
        return getattr(user, 'patient_profile', None)
    if user.role == UserRole.DOCTOR:
        return getattr(user, 'doctor_profile', None)
    return None


def get_profile_completion(user, profile=None):
    """Compute onboarding state without persisting derived data."""
    profile = profile or get_profile_for_user(user)
    required = PROFILE_REQUIRED_FIELDS.get(user.role, ())
    missing = []
    for field in required:
        owner = user if hasattr(user, field) else profile
        value = getattr(owner, field, None) if owner is not None else None
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    total = len(required)
    percentage = 0 if not total else round(((total - len(missing)) / total) * 100)
    return {
        'is_complete': bool(required) and not missing,
        'completion_percentage': percentage,
        'missing_fields': missing,
    }


@transaction.atomic
def repair_missing_patient_profile(user):
    """Create only a genuinely missing patient profile; safe to call repeatedly."""
    user_id = getattr(user, 'pk', user)
    try:
        locked_user = User.objects.select_for_update().get(pk=user_id)
    except User.DoesNotExist as exc:
        raise ValidationError({'user': 'The user does not exist.'}) from exc
    if locked_user.role != UserRole.PATIENT:
        raise ValidationError({'user': 'Only a patient user can receive a patient profile.'})

    existing = PatientProfile.objects.filter(user=locked_user).first()
    if existing is not None:
        return existing, False

    profile = PatientProfile(user=locked_user)
    profile.full_clean()
    try:
        with transaction.atomic():
            profile.save(force_insert=True)
    except IntegrityError:
        # Another worker may have repaired the same account concurrently.
        return PatientProfile.objects.get(user=locked_user), False
    return profile, True


@transaction.atomic
def update_own_profile(*, user, profile, validated_data):
    """Update only pre-validated fields and preserve ownership/system fields."""
    locked = type(profile).objects.select_for_update().select_related('user').get(
        pk=profile.pk, user=user,
    )
    for field, value in validated_data.items():
        setattr(locked, field, value.strip() if isinstance(value, str) else value)
    locked.full_clean()
    locked.save(update_fields=(*validated_data.keys(), 'updated_at'))
    return locked


@transaction.atomic
def assign_doctor_to_patient(*, doctor_user, patient_user, assigned_at=None):
    """Create a new active assignment while preserving all ended history."""
    locked_users = {
        user.pk: user
        for user in User.objects.select_for_update().filter(
            pk__in=(doctor_user.pk, patient_user.pk),
        )
    }
    doctor_user = locked_users.get(doctor_user.pk)
    patient_user = locked_users.get(patient_user.pk)
    if doctor_user is None or patient_user is None:
        raise ValidationError('The doctor and patient users must exist.')
    if doctor_user.pk == patient_user.pk:
        raise ValidationError('A patient cannot be assigned to themselves.')
    if doctor_user.role != UserRole.DOCTOR or not doctor_user.is_active:
        raise ValidationError({'doctor_user': 'An active user with the doctor role is required.'})
    if patient_user.role != UserRole.PATIENT or not patient_user.is_active:
        raise ValidationError({'patient_user': 'An active user with the patient role is required.'})

    try:
        doctor = DoctorProfile.objects.select_for_update().get(user=doctor_user)
    except DoctorProfile.DoesNotExist as exc:
        raise ValidationError({'doctor_user': 'The doctor user must have a doctor profile.'}) from exc
    try:
        patient = PatientProfile.objects.select_for_update().get(user=patient_user)
    except PatientProfile.DoesNotExist as exc:
        raise ValidationError({'patient_user': 'The patient user must have a patient profile.'}) from exc

    if PatientDoctorAssignment.objects.select_for_update().filter(
        doctor=doctor,
        patient=patient,
        status=AssignmentStatus.ACTIVE,
    ).exists():
        raise ValidationError('An active assignment already exists for this doctor and patient.')

    assignment = PatientDoctorAssignment(
        doctor=doctor,
        patient=patient,
        assigned_at=assigned_at or timezone.now(),
    )
    assignment.full_clean()
    try:
        with transaction.atomic():
            assignment.save(force_insert=True)
    except IntegrityError as exc:
        raise ValidationError(
            'An active assignment already exists for this doctor and patient.',
        ) from exc
    return assignment


@transaction.atomic
def end_doctor_patient_assignment(assignment, *, ended_at=None):
    """End an active assignment without rewriting its historical start."""
    assignment_id = getattr(assignment, 'pk', assignment)
    try:
        locked = PatientDoctorAssignment.objects.select_for_update().get(pk=assignment_id)
    except PatientDoctorAssignment.DoesNotExist as exc:
        raise ValidationError('The assignment does not exist.') from exc
    if locked.status != AssignmentStatus.ACTIVE:
        raise ValidationError('Only an active assignment can be ended.')

    locked.status = AssignmentStatus.ENDED
    locked.ended_at = ended_at or timezone.now()
    locked.full_clean()
    locked.save(update_fields=('status', 'ended_at', 'updated_at'))

    if isinstance(assignment, PatientDoctorAssignment):
        assignment.status = locked.status
        assignment.ended_at = locked.ended_at
        assignment.updated_at = locked.updated_at
        return assignment
    return locked


@transaction.atomic
def change_user_role(user, new_role):
    """Change a role only when no existing profile would become inconsistent."""
    if new_role not in UserRole.values:
        raise ValidationError({'role': 'Unknown user role.'})
    locked = User.objects.select_for_update().get(pk=user.pk)
    if locked.role == new_role:
        return locked
    locked.role = new_role
    locked.save(update_fields=('role', 'updated_at'))
    user.role = locked.role
    user.updated_at = locked.updated_at
    return user
