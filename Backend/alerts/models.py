import json
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AlertType(models.TextChoices):
    HYPERTENSION = 'HYPERTENSION', _('Blood pressure')
    DIABETES = 'DIABETES', _('Blood glucose')
    HEART_RATE = 'HEART_RATE', _('Heart rate')
    GENERAL = 'GENERAL', _('General')


class AlertLevel(models.TextChoices):
    INFO = 'INFO', _('Info')
    LOW = 'LOW', _('Low')
    MEDIUM = 'MEDIUM', _('Medium')
    HIGH = 'HIGH', _('High')
    CRITICAL = 'CRITICAL', _('Critical')


class AlertSource(models.TextChoices):
    SYSTEM_RULE = 'SYSTEM_RULE', _('System rule')
    DOCTOR = 'DOCTOR', _('Doctor')
    MANUAL = 'MANUAL', _('Manual')


class AlertStatus(models.TextChoices):
    OPEN = 'OPEN', _('Open')
    ACKNOWLEDGED = 'ACKNOWLEDGED', _('Acknowledged')
    RESOLVED = 'RESOLVED', _('Resolved')
    DISMISSED = 'DISMISSED', _('Dismissed')


class MedicalAlert(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        'profiles.PatientProfile', on_delete=models.PROTECT,
        related_name='medical_alerts', verbose_name=_('patient profile'),
    )
    type = models.CharField(_('type'), max_length=20, choices=AlertType.choices, default=AlertType.GENERAL)
    niveau = models.CharField(max_length=10, choices=AlertLevel.choices, default=AlertLevel.INFO)
    status = models.CharField(max_length=15, choices=AlertStatus.choices, default=AlertStatus.OPEN)
    source = models.CharField(_('source'), max_length=20, choices=AlertSource.choices, default=AlertSource.SYSTEM_RULE)
    rule_code = models.CharField(max_length=100)
    rule_name = models.CharField(max_length=255)
    message = models.TextField(_('message'))
    source_type = models.CharField(max_length=100)
    source_id = models.UUIDField(null=True, blank=True)
    observed_value = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=30, blank=True)
    detected_at = models.DateTimeField(default=timezone.now)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='handled_medical_alerts',
    )
    status_reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        ordering = ('-detected_at', '-created_at')
        indexes = [
            models.Index(fields=('patient', 'status', '-detected_at'), name='alert_patient_status_idx'),
            models.Index(fields=('rule_code', '-detected_at'), name='alert_rule_date_idx'),
            models.Index(fields=('source_type', 'source_id'), name='alert_source_idx'),
            models.Index(fields=('niveau', '-detected_at'), name='alert_level_date_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=('source_type', 'source_id', 'rule_code'),
                condition=Q(source_id__isnull=False),
                name='unique_alert_source_rule',
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=AlertStatus.OPEN, acknowledged_at__isnull=True, resolved_at__isnull=True, dismissed_at__isnull=True)
                    | Q(status=AlertStatus.ACKNOWLEDGED, acknowledged_at__isnull=False, resolved_at__isnull=True, dismissed_at__isnull=True, handled_by__isnull=False)
                    | Q(status=AlertStatus.RESOLVED, acknowledged_at__isnull=False, resolved_at__isnull=False, dismissed_at__isnull=True, handled_by__isnull=False)
                    | Q(status=AlertStatus.DISMISSED, resolved_at__isnull=True, dismissed_at__isnull=False, handled_by__isnull=False)
                ),
                name='alert_status_dates_consistent',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        for field in ('rule_code', 'rule_name', 'message', 'source_type'):
            value = getattr(self, field, '').strip()
            setattr(self, field, value)
            if not value:
                errors[field] = _('This field cannot be empty.')
        if not isinstance(self.metadata, dict):
            errors['metadata'] = _('Metadata must be a JSON object.')
        elif len(json.dumps(self.metadata, default=str).encode('utf-8')) > 8192:
            errors['metadata'] = _('Metadata must not exceed 8192 bytes.')
        if self.status == AlertStatus.OPEN and any((self.acknowledged_at, self.resolved_at, self.dismissed_at)):
            errors['status'] = _('An open alert cannot have transition dates.')
        if self.status == AlertStatus.ACKNOWLEDGED and (not self.acknowledged_at or self.resolved_at or self.dismissed_at or not self.handled_by_id):
            errors['status'] = _('An acknowledged alert requires its doctor and date only.')
        if self.status == AlertStatus.RESOLVED and (not self.acknowledged_at or not self.resolved_at or self.dismissed_at or not self.handled_by_id):
            errors['status'] = _('A resolved alert requires acknowledgement and resolution data.')
        if self.status == AlertStatus.DISMISSED and (not self.dismissed_at or self.resolved_at or not self.handled_by_id or not self.status_reason.strip()):
            errors['status'] = _('A dismissed alert requires its doctor, date and reason.')
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.rule_code} - {self.niveau} - {self.patient.user.email}'
