from accounts.models import UserRole

from .models import AssignmentStatus, PatientDoctorAssignment, PatientProfile


def doctor_can_access_patient(doctor_user, patient_user):
    """Return whether an active doctor currently follows an active patient."""
    if not doctor_user or not patient_user:
        return False
    if not doctor_user.is_active or not patient_user.is_active:
        return False
    if doctor_user.role != UserRole.DOCTOR or patient_user.role != UserRole.PATIENT:
        return False
    return PatientDoctorAssignment.objects.filter(
        doctor__user=doctor_user,
        patient__user=patient_user,
        status=AssignmentStatus.ACTIVE,
        ended_at__isnull=True,
    ).exists()


def active_patient_profiles_for_doctor(doctor_user):
    """Return an SQL queryset limited to a doctor's current active patients."""
    if (
        not doctor_user
        or not doctor_user.is_active
        or doctor_user.role != UserRole.DOCTOR
    ):
        return PatientProfile.objects.none()
    return PatientProfile.objects.filter(
        user__is_active=True,
        user__role=UserRole.PATIENT,
        doctor_assignments__doctor__user=doctor_user,
        doctor_assignments__status=AssignmentStatus.ACTIVE,
        doctor_assignments__ended_at__isnull=True,
    ).distinct()


def active_doctor_users_for_patient(patient_user):
    """Return active doctor users currently assigned to an active patient."""
    from accounts.models import User

    if (
        not patient_user or not patient_user.is_active
        or patient_user.role != UserRole.PATIENT
    ):
        return User.objects.none()
    return User.objects.filter(
        is_active=True,
        role=UserRole.DOCTOR,
        doctor_profile__patient_assignments__patient__user=patient_user,
        doctor_profile__patient_assignments__status=AssignmentStatus.ACTIVE,
        doctor_profile__patient_assignments__ended_at__isnull=True,
    ).distinct()


def active_assignments_for_doctor(doctor_user):
    """Return current, active-patient assignments without N+1 queries."""
    return PatientDoctorAssignment.objects.select_related(
        'patient__user', 'doctor__user',
    ).filter(
        doctor__user=doctor_user,
        doctor__user__is_active=True,
        patient__user__is_active=True,
        status=AssignmentStatus.ACTIVE,
        ended_at__isnull=True,
    )


def active_assignments_for_patient(patient_user):
    """Return current, active-doctor assignments without N+1 queries."""
    return PatientDoctorAssignment.objects.select_related(
        'patient__user', 'doctor__user',
    ).filter(
        patient__user=patient_user,
        patient__user__is_active=True,
        doctor__user__is_active=True,
        status=AssignmentStatus.ACTIVE,
        ended_at__isnull=True,
    )


def assignment_history_for_user(user):
    queryset = PatientDoctorAssignment.objects.select_related(
        'patient__user', 'doctor__user',
    )
    if not user or not user.is_active:
        return queryset.none()
    if user.role == UserRole.PATIENT:
        return queryset.filter(patient__user=user)
    if user.role == UserRole.DOCTOR:
        return queryset.filter(doctor__user=user)
    return queryset.none()
