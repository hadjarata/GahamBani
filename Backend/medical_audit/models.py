import uuid

from django.core.exceptions import ValidationError
from django.db import models


class AuditAction(models.TextChoices):
    VIEW = 'VIEW', 'View'
    LIST = 'LIST', 'List'
    CREATE = 'CREATE', 'Create'
    UPDATE = 'UPDATE', 'Update'
    DOWNLOAD = 'DOWNLOAD', 'Download'
    ACCESS_DENIED = 'ACCESS_DENIED', 'Access denied'


class AuditResult(models.TextChoices):
    SUCCESS = 'SUCCESS', 'Success'
    DENIED = 'DENIED', 'Denied'


class AuditDomain(models.TextChoices):
    MONITORING = 'MONITORING', 'Monitoring'
    MEDICAL_RECORDS = 'MEDICAL_RECORDS', 'Medical records'
    ALERTS = 'ALERTS', 'Alerts'
    NOTIFICATIONS = 'NOTIFICATIONS', 'Notifications'
    ANALYTICS = 'ANALYTICS', 'Analytics'
    PROFILES = 'PROFILES', 'Profiles'


class ImmutableAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Medical audit events are append-only.')

    def delete(self):
        raise ValidationError('Medical audit events cannot be deleted.')


class MedicalAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='medical_audit_events',
    )
    actor_reference = models.UUIDField(null=True, blank=True, editable=False)
    actor_role = models.CharField(max_length=20, blank=True)
    patient = models.ForeignKey(
        'profiles.PatientProfile', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='medical_audit_events',
    )
    patient_reference = models.UUIDField(null=True, blank=True, editable=False)
    action = models.CharField(max_length=20, choices=AuditAction.choices)
    result = models.CharField(
        max_length=10, choices=AuditResult.choices, default=AuditResult.SUCCESS,
    )
    domain = models.CharField(max_length=30, choices=AuditDomain.choices)
    resource_type = models.CharField(max_length=100)
    resource_id = models.UUIDField(null=True, blank=True)
    http_method = models.CharField(max_length=10, blank=True)
    endpoint = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    changes = models.JSONField(default=dict, blank=True)

    objects = ImmutableAuditQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('-created_at',), name='audit_created_idx'),
            models.Index(fields=('actor', '-created_at'), name='audit_actor_date_idx'),
            models.Index(fields=('patient', '-created_at'), name='audit_patient_date_idx'),
            models.Index(fields=('resource_type', 'resource_id'), name='audit_resource_idx'),
            models.Index(fields=('action', '-created_at'), name='audit_action_date_idx'),
            models.Index(fields=('result', '-created_at'), name='audit_result_date_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Medical audit events are append-only.')
        if self.actor_id and not self.actor_reference:
            self.actor_reference = self.actor_id
        if self.patient_id and not self.patient_reference:
            self.patient_reference = self.patient_id
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Medical audit events cannot be deleted.')

    def __str__(self):
        return f'{self.created_at} {self.action} {self.resource_type}:{self.resource_id}'
