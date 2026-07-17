import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SexChoices(models.TextChoices):
    MALE = 'MALE', _('Male')
    FEMALE = 'FEMALE', _('Female')
    OTHER = 'OTHER', _('Other')


class PatientProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='patient_profile',
        verbose_name=_('user'),
    )
    date_naissance = models.DateField(_('date of birth'), blank=True, null=True)
    sexe = models.CharField(
        _('sex'),
        max_length=10,
        choices=SexChoices.choices,
        blank=True,
        null=True,
    )
    poids = models.DecimalField(
        _('weight'),
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
    )
    taille = models.DecimalField(
        _('height'),
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
    )
    antecedents = models.TextField(_('medical history'), blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('patient profile')
        verbose_name_plural = _('patient profiles')
        ordering = ['-created_at']

    def __str__(self):
        return f'Patient profile for {self.user.email}'

    def clean(self):
        super().clean()
        from accounts.models import UserRole

        if self.user_id and self.user.role != UserRole.PATIENT:
            raise ValidationError({'user': _('The selected user must have the patient role.')})
        if self.user_id and hasattr(self.user, 'doctor_profile'):
            raise ValidationError({'user': _('This user already has a doctor profile.')})


class DoctorProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='doctor_profile',
        verbose_name=_('user'),
    )
    specialite = models.CharField(_('specialty'), max_length=255)
    numero_ordre = models.CharField(_('registration number'), max_length=100, unique=True)
    hopital = models.CharField(_('hospital'), max_length=255)
    annees_experience = models.PositiveSmallIntegerField(_('years of experience'))
    patients = models.ManyToManyField(
        PatientProfile,
        through='PatientDoctorAssignment',
        related_name='doctors',
        blank=True,
        verbose_name=_('patients'),
    )
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('doctor profile')
        verbose_name_plural = _('doctor profiles')
        ordering = ['-created_at']

    def __str__(self):
        return f'Doctor profile for {self.user.email}'

    def clean(self):
        super().clean()
        from accounts.models import UserRole

        if self.user_id and self.user.role != UserRole.DOCTOR:
            raise ValidationError({'user': _('The selected user must have the doctor role.')})
        if self.user_id and hasattr(self.user, 'patient_profile'):
            raise ValidationError({'user': _('This user already has a patient profile.')})


class AssignmentStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', _('Active')
    ENDED = 'ENDED', _('Ended')


class PatientDoctorAssignment(models.Model):
    """Represent a doctor's responsibility for following a patient."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.PROTECT,
        related_name='doctor_assignments',
        verbose_name=_('patient profile'),
    )
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.PROTECT,
        related_name='patient_assignments',
        verbose_name=_('doctor profile'),
    )
    status = models.CharField(
        _('status'),
        max_length=10,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ACTIVE,
        db_index=True,
    )
    assigned_at = models.DateTimeField(_('assigned at'), default=timezone.now)
    ended_at = models.DateTimeField(_('ended at'), null=True, blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('patient-doctor assignment')
        verbose_name_plural = _('patient-doctor assignments')
        ordering = ['-assigned_at']
        constraints = [
            models.UniqueConstraint(
                fields=['patient', 'doctor'],
                condition=Q(status=AssignmentStatus.ACTIVE),
                name='unique_active_patient_doctor_assignment',
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=AssignmentStatus.ACTIVE, ended_at__isnull=True)
                    | Q(status=AssignmentStatus.ENDED, ended_at__isnull=False)
                ),
                name='assignment_status_matches_end_date',
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=models.F('assigned_at')),
                name='assignment_end_not_before_start',
            ),
        ]
        indexes = [
            models.Index(fields=['doctor', 'status'], name='prof_assign_doc_status_idx'),
            models.Index(fields=['patient', 'status'], name='prof_assign_pat_status_idx'),
            models.Index(
                fields=['patient', 'doctor', '-assigned_at'],
                name='prof_assign_pair_hist_idx',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.patient_id and self.doctor_id:
            from accounts.models import UserRole

            patient_user = self.patient.user
            doctor_user = self.doctor.user
            if patient_user.role != UserRole.PATIENT:
                errors['patient'] = _('The patient profile user must have the patient role.')
            elif not patient_user.is_active:
                errors['patient'] = _('The patient user must be active.')
            if doctor_user.role != UserRole.DOCTOR:
                errors['doctor'] = _('The doctor profile user must have the doctor role.')
            elif not doctor_user.is_active:
                errors['doctor'] = _('The doctor user must be active.')
            if patient_user.pk == doctor_user.pk:
                errors['doctor'] = _('A patient cannot be assigned to themselves.')

        if self.status == AssignmentStatus.ACTIVE and self.ended_at is not None:
            errors['ended_at'] = _('An active assignment cannot have an end date.')
        elif self.status == AssignmentStatus.ENDED and self.ended_at is None:
            errors['ended_at'] = _('An ended assignment must have an end date.')
        if self.ended_at and self.assigned_at and self.ended_at < self.assigned_at:
            errors['ended_at'] = _('The end date cannot be earlier than the assignment date.')
        if self.pk:
            previous_status = type(self).objects.filter(pk=self.pk).values_list(
                'status',
                flat=True,
            ).first()
            if previous_status == AssignmentStatus.ENDED and self.status == AssignmentStatus.ACTIVE:
                errors['status'] = _(
                    'An ended assignment cannot be reactivated; create a new assignment.',
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.doctor.user.email} -> {self.patient.user.email} ({self.status})'
