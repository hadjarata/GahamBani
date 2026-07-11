import uuid

from django.db import models
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
        on_delete=models.CASCADE,
        related_name='patient_profile',
        verbose_name=_('user'),
    )
    date_naissance = models.DateField(_('date of birth'))
    sexe = models.CharField(
        _('sex'),
        max_length=10,
        choices=SexChoices.choices,
        default=SexChoices.OTHER,
    )
    poids = models.DecimalField(_('weight'), max_digits=6, decimal_places=2)
    taille = models.DecimalField(_('height'), max_digits=5, decimal_places=2)
    antecedents = models.TextField(_('medical history'), blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('patient profile')
        verbose_name_plural = _('patient profiles')
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user'], name='unique_patient_profile_user'),
        ]

    def __str__(self):
        return f'Patient profile for {self.user.email}'


class DoctorProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='doctor_profile',
        verbose_name=_('user'),
    )
    specialite = models.CharField(_('specialty'), max_length=255)
    numero_ordre = models.CharField(_('registration number'), max_length=100, unique=True)
    hopital = models.CharField(_('hospital'), max_length=255)
    annees_experience = models.PositiveSmallIntegerField(_('years of experience'))
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('doctor profile')
        verbose_name_plural = _('doctor profiles')
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user'], name='unique_doctor_profile_user'),
        ]

    def __str__(self):
        return f'Doctor profile for {self.user.email}'
