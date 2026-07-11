import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AlertType(models.TextChoices):
    HYPERTENSION = 'HYPERTENSION', _('Hypertension')
    DIABETES = 'DIABETES', _('Diabetes')
    HEART_RATE = 'HEART_RATE', _('Heart rate')
    GENERAL = 'GENERAL', _('General')


class AlertLevel(models.TextChoices):
    INFO = 'INFO', _('Info')
    WARNING = 'WARNING', _('Warning')
    CRITICAL = 'CRITICAL', _('Critical')


class AlertSource(models.TextChoices):
    SYSTEM_RULE = 'SYSTEM_RULE', _('System rule')
    DOCTOR = 'DOCTOR', _('Doctor')
    MANUAL = 'MANUAL', _('Manual')


class AlertStatus(models.TextChoices):
    NEW = 'NEW', _('New')
    SEEN = 'SEEN', _('Seen')
    RESOLVED = 'RESOLVED', _('Resolved')
    DISMISSED = 'DISMISSED', _('Dismissed')


class MedicalAlert(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        'profiles.PatientProfile',
        on_delete=models.CASCADE,
        related_name='medical_alerts',
        verbose_name=_('patient profile'),
    )
    type = models.CharField(
        _('type'),
        max_length=20,
        choices=AlertType.choices,
        default=AlertType.GENERAL,
    )
    niveau = models.CharField(
        _('level'),
        max_length=10,
        choices=AlertLevel.choices,
        default=AlertLevel.INFO,
    )
    status = models.CharField(
        _('status'),
        max_length=10,
        choices=AlertStatus.choices,
        default=AlertStatus.NEW,
    )
    message = models.TextField(_('message'))
    source = models.CharField(
        _('source'),
        max_length=20,
        choices=AlertSource.choices,
        default=AlertSource.SYSTEM_RULE,
    )
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('medical alert')
        verbose_name_plural = _('medical alerts')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient', 'created_at']),
        ]

    def __str__(self):
        return f'Alerte {self.type} - {self.niveau} - {self.patient.user.email}'
