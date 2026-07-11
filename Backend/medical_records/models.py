import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class BloodGroupChoices(models.TextChoices):
    A_POSITIVE = 'A_POSITIVE', _('A+')
    A_NEGATIVE = 'A_NEGATIVE', _('A-')
    B_POSITIVE = 'B_POSITIVE', _('B+')
    B_NEGATIVE = 'B_NEGATIVE', _('B-')
    AB_POSITIVE = 'AB_POSITIVE', _('AB+')
    AB_NEGATIVE = 'AB_NEGATIVE', _('AB-')
    O_POSITIVE = 'O_POSITIVE', _('O+')
    O_NEGATIVE = 'O_NEGATIVE', _('O-')
    UNKNOWN = 'UNKNOWN', _('Unknown')


class SeverityChoices(models.TextChoices):
    LOW = 'LOW', _('Low')
    MEDIUM = 'MEDIUM', _('Medium')
    HIGH = 'HIGH', _('High')
    CRITICAL = 'CRITICAL', _('Critical')


class StatusChoices(models.TextChoices):
    ACTIVE = 'ACTIVE', _('Active')
    INACTIVE = 'INACTIVE', _('Inactive')
    CONTROLLED = 'CONTROLLED', _('Controlled')


class MedicalRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.OneToOneField(
        'profiles.PatientProfile',
        on_delete=models.CASCADE,
        related_name='medical_record',
        verbose_name=_('patient profile'),
    )
    groupe_sanguin = models.CharField(
        _('blood group'),
        max_length=20,
        choices=BloodGroupChoices.choices,
        default=BloodGroupChoices.UNKNOWN,
    )
    allergies_text = models.TextField(_('allergies'), blank=True)
    antecedents_familiaux = models.TextField(_('family medical history'), blank=True)
    maladies_chroniques = models.TextField(_('chronic diseases'), blank=True)
    traitements_actuels = models.TextField(_('current treatments'), blank=True)
    notes_medicales = models.TextField(_('medical notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('medical record')
        verbose_name_plural = _('medical records')
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['patient'], name='unique_medical_record_patient'),
        ]

    def __str__(self):
        patient_name = self.patient.user.email if self.patient and self.patient.user else str(self.patient)
        return f'Medical record ({self.groupe_sanguin}) for {patient_name}'


class ChronicDisease(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.CASCADE,
        related_name='chronic_diseases',
        verbose_name=_('medical record'),
    )
    nom_maladie = models.CharField(_('disease name'), max_length=255, db_index=True)
    date_diagnostic = models.DateField(_('diagnosis date'), null=True, blank=True)
    gravite = models.CharField(
        _('severity'),
        max_length=10,
        choices=SeverityChoices.choices,
        default=SeverityChoices.MEDIUM,
    )
    statut = models.CharField(
        _('status'),
        max_length=12,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE,
        db_index=True,
    )
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('chronic disease')
        verbose_name_plural = _('chronic diseases')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.nom_maladie} ({self.gravite})'


class Allergy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.CASCADE,
        related_name='allergies',
        verbose_name=_('medical record'),
    )
    nom = models.CharField(_('name'), max_length=255)
    gravite = models.CharField(
        _('severity'),
        max_length=10,
        choices=SeverityChoices.choices[:3],
        default=SeverityChoices.MEDIUM,
    )
    reaction = models.TextField(_('reaction'))
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('allergy')
        verbose_name_plural = _('allergies')
        ordering = ['-created_at']

    def __str__(self):
        return f'Allergy {self.nom} ({self.gravite}) for {self.medical_record.patient.user.email}'


class MedicalNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.CASCADE,
        related_name='medical_notes',
        verbose_name=_('medical record'),
    )
    auteur = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='medical_notes',
        verbose_name=_('author'),
    )
    contenu = models.TextField(_('content'))
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)

    class Meta:
        verbose_name = _('medical note')
        verbose_name_plural = _('medical notes')
        ordering = ['-created_at']

    def __str__(self):
        return f'Note by {self.auteur.email} for {self.medical_record.patient.user.email} on {self.created_at:%Y-%m-%d}'
