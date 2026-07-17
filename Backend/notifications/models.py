import json
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class NotificationType(models.TextChoices):
    MEDICAL_ALERT_CREATED = 'MEDICAL_ALERT_CREATED', 'Medical alert created'
    ALERT_ACKNOWLEDGED = 'ALERT_ACKNOWLEDGED', 'Alert acknowledged'
    ALERT_RESOLVED = 'ALERT_RESOLVED', 'Alert resolved'
    ALERT_DISMISSED = 'ALERT_DISMISSED', 'Alert dismissed'
    SYSTEM = 'SYSTEM', 'System'


class NotificationPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    NORMAL = 'NORMAL', 'Normal'
    HIGH = 'HIGH', 'High'
    CRITICAL = 'CRITICAL', 'Critical'


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='notifications',
    )
    recipient_reference = models.UUIDField(editable=False)
    patient = models.ForeignKey(
        'profiles.PatientProfile', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='notifications',
    )
    patient_reference = models.UUIDField(null=True, blank=True, editable=False)
    type = models.CharField(max_length=30, choices=NotificationType.choices)
    priority = models.CharField(
        max_length=10, choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
    )
    title = models.CharField(max_length=120)
    message = models.CharField(max_length=500)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    source_domain = models.CharField(max_length=50)
    source_type = models.CharField(max_length=100)
    source_id = models.UUIDField()
    event_code = models.CharField(max_length=100)
    metadata = models.JSONField(default=dict, blank=True)
    public_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at', '-id')
        indexes = [
            models.Index(fields=('recipient', 'is_read', '-created_at'), name='notif_rec_read_date_idx'),
            models.Index(fields=('recipient', '-created_at'), name='notif_rec_date_idx'),
            models.Index(fields=('type', '-created_at'), name='notif_type_date_idx'),
            models.Index(fields=('source_type', 'source_id'), name='notif_source_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=('recipient_reference', 'event_code', 'source_type', 'source_id'),
                name='unique_notification_event_recipient',
            ),
            models.CheckConstraint(
                condition=(Q(is_read=False, read_at__isnull=True) | Q(is_read=True, read_at__isnull=False)),
                name='notification_read_state_consistent',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self._state.adding and not self.recipient_id:
            errors['recipient'] = 'A recipient is required.'
        if self.recipient_id and not self.recipient.is_active:
            errors['recipient'] = 'The recipient must be active.'
        for field in ('title', 'message', 'source_domain', 'source_type', 'event_code'):
            value = getattr(self, field, '').strip()
            setattr(self, field, value)
            if not value:
                errors[field] = 'This field cannot be empty.'
        if self.is_read != bool(self.read_at):
            errors['read_at'] = 'Read state and date must be consistent.'
        for field in ('metadata', 'public_metadata'):
            value = getattr(self, field)
            if not isinstance(value, dict):
                errors[field] = 'Metadata must be a JSON object.'
            elif len(json.dumps(value, default=str).encode('utf-8')) > 8192:
                errors[field] = 'Metadata must not exceed 8192 bytes.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.recipient_id and not self.recipient_reference:
            self.recipient_reference = self.recipient_id
        if self.patient_id and not self.patient_reference:
            self.patient_reference = self.patient_id
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.type} -> {self.recipient_reference}'
