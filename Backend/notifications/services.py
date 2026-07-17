from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from alerts.models import AlertLevel
from medical_audit.models import AuditAction, AuditDomain
from medical_audit.services import record_medical_audit_event
from profiles.selectors import active_doctor_users_for_patient

from .models import Notification, NotificationPriority, NotificationType
from .sanitizers import sanitize_metadata


ALERT_PRIORITY_MAP = {
    AlertLevel.INFO: NotificationPriority.LOW,
    AlertLevel.LOW: NotificationPriority.LOW,
    AlertLevel.MEDIUM: NotificationPriority.NORMAL,
    AlertLevel.HIGH: NotificationPriority.HIGH,
    AlertLevel.CRITICAL: NotificationPriority.CRITICAL,
}


def _audit(notification, *, action, actor=None, request=None, metadata=None):
    details = {
        'event_code': notification.event_code,
        'notification_id': str(notification.pk),
        'notification_type': notification.type,
        'priority': notification.priority,
        'source_type': notification.source_type,
        **(metadata or {}),
    }
    return record_medical_audit_event(
        action=action, domain=AuditDomain.NOTIFICATIONS,
        resource_type=Notification._meta.label_lower,
        resource_id=notification.pk, actor=actor,
        patient=notification.patient, request=request, metadata=details,
    )


@transaction.atomic
def create_notification(
    *, recipient, notification_type, priority, title, message,
    source_domain, source_type, source_id, event_code,
    patient=None, metadata=None, public_metadata=None, actor=None, request=None,
):
    if not recipient or not recipient.is_active:
        return None
    candidate = Notification(
        recipient=recipient, recipient_reference=recipient.pk,
        patient=patient, patient_reference=getattr(patient, 'pk', None),
        type=notification_type, priority=priority,
        title=title, message=message,
        source_domain=source_domain, source_type=source_type,
        source_id=source_id, event_code=event_code,
        metadata=sanitize_metadata(metadata or {}),
        public_metadata=sanitize_metadata(public_metadata or {}, public=True),
    )
    candidate.full_clean(validate_constraints=False)
    notification, created = Notification.objects.get_or_create(
        recipient_reference=recipient.pk,
        event_code=event_code,
        source_type=source_type,
        source_id=source_id,
        defaults={
            'recipient': recipient, 'patient': patient,
            'patient_reference': getattr(patient, 'pk', None),
            'type': notification_type, 'priority': priority,
            'title': candidate.title, 'message': candidate.message,
            'source_domain': candidate.source_domain,
            'metadata': candidate.metadata,
            'public_metadata': candidate.public_metadata,
        },
    )
    if created:
        _audit(notification, action=AuditAction.CREATE, actor=actor, request=request)
    return notification


def _alert_notification(alert, recipient, *, notification_type, title, message, actor=None, request=None):
    return create_notification(
        recipient=recipient,
        notification_type=notification_type,
        priority=ALERT_PRIORITY_MAP[alert.niveau],
        title=title,
        message=message,
        source_domain='ALERTS',
        source_type=alert._meta.label_lower,
        source_id=alert.pk,
        event_code=notification_type,
        patient=alert.patient,
        metadata={'rule_code': alert.rule_code, 'recipient_role': recipient.role},
        public_metadata={'alert_id': str(alert.pk), 'alert_severity': alert.niveau},
        actor=actor,
        request=request,
    )


@transaction.atomic
def notify_alert_created(alert, *, actor=None, request=None):
    notifications = []
    patient_user = alert.patient.user
    if patient_user.is_active:
        notifications.append(_alert_notification(
            alert, patient_user,
            notification_type=NotificationType.MEDICAL_ALERT_CREATED,
            title='Nouvelle alerte',
            message='Une nouvelle mesure nécessite votre attention dans l’application.',
            actor=actor, request=request,
        ))
    for doctor_user in active_doctor_users_for_patient(patient_user).iterator():
        notifications.append(_alert_notification(
            alert, doctor_user,
            notification_type=NotificationType.MEDICAL_ALERT_CREATED,
            title='Alerte patient à vérifier',
            message='Une nouvelle alerte concernant un patient suivi nécessite une vérification.',
            actor=actor, request=request,
        ))
    return [item for item in notifications if item is not None]


@transaction.atomic
def notify_alert_transition(alert, transition, *, actor=None, request=None):
    mapping = {
        'ACKNOWLEDGE': (
            NotificationType.ALERT_ACKNOWLEDGED,
            'Alerte prise en compte',
            'Un professionnel a pris connaissance de votre alerte.',
        ),
        'RESOLVE': (
            NotificationType.ALERT_RESOLVED,
            'Suivi de l’alerte mis à jour',
            'La prise en charge de votre alerte a été clôturée dans l’application.',
        ),
        'DISMISS': (
            NotificationType.ALERT_DISMISSED,
            'Statut de l’alerte mis à jour',
            'Votre alerte a été classée après vérification.',
        ),
    }
    if transition not in mapping:
        raise ValueError('Unsupported alert notification transition.')
    if not alert.patient.user.is_active:
        return None
    notification_type, title, message = mapping[transition]
    return _alert_notification(
        alert, alert.patient.user,
        notification_type=notification_type, title=title, message=message,
        actor=actor, request=request,
    )


@transaction.atomic
def mark_notification_as_read(notification, *, recipient, request=None):
    locked = Notification.objects.select_for_update().select_related('patient').get(pk=notification.pk)
    if locked.recipient_id != recipient.pk or not recipient.is_active:
        raise ValidationError('Only the active recipient may read this notification.')
    if not locked.is_read:
        locked.is_read = True
        locked.read_at = timezone.now()
        locked.full_clean()
        locked.save(update_fields=('is_read', 'read_at', 'updated_at'))
        _audit(locked, action=AuditAction.UPDATE, actor=recipient, request=request, metadata={'operation': 'MARK_AS_READ'})
    return locked


@transaction.atomic
def mark_all_notifications_as_read(*, recipient, request=None):
    if not recipient.is_active:
        raise ValidationError('An active recipient is required.')
    read_at = timezone.now()
    updated = Notification.objects.filter(
        recipient=recipient, is_read=False,
    ).update(is_read=True, read_at=read_at, updated_at=read_at)
    record_medical_audit_event(
        action=AuditAction.UPDATE, domain=AuditDomain.NOTIFICATIONS,
        resource_type=Notification._meta.label_lower,
        actor=recipient, request=request,
        metadata={'operation': 'MARK_ALL_AS_READ', 'updated_count': updated},
    )
    return updated
