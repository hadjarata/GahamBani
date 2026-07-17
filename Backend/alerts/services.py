from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import UserRole
from medical_audit.models import AuditAction, AuditDomain
from medical_audit.services import record_medical_audit_event
from profiles.selectors import doctor_can_access_patient
from notifications.services import notify_alert_created, notify_alert_transition

from .models import AlertSource, AlertStatus, MedicalAlert
from .rules import rules_for_measurement


def _audit_alert(alert, *, action, actor=None, request=None, transition=None):
    metadata = {
        'rule_code': alert.rule_code,
        'severity': alert.niveau,
        'alert_id': str(alert.pk),
        'source_type': alert.source_type,
    }
    if transition:
        metadata['transition'] = transition
    return record_medical_audit_event(
        action=action, domain=AuditDomain.ALERTS,
        resource_type=MedicalAlert._meta.label_lower, resource_id=alert.pk,
        actor=actor, patient=alert.patient, request=request, metadata=metadata,
    )


@transaction.atomic
def evaluate_measurement_for_alerts(measurement, *, actor=None, request=None):
    """Evaluate validated persisted data and upsert one alert per source/rule."""
    if not measurement.pk:
        raise ValidationError('The measurement must be saved before evaluation.')
    model_class = type(measurement)
    measurement = model_class.objects.select_for_update().select_related('patient__user').get(
        pk=measurement.pk,
    )
    source_type = measurement._meta.label_lower
    existing = {
        alert.rule_code: alert
        for alert in MedicalAlert.objects.select_for_update().filter(
            source_type=source_type, source_id=measurement.pk,
        )
    }
    triggered = []
    triggered_codes = set()
    evaluated_at = timezone.now().isoformat()
    for rule in rules_for_measurement(measurement):
        result = rule.evaluate(measurement)
        if result is None:
            continue
        triggered_codes.add(result.rule_code)
        alert = existing.get(result.rule_code)
        created = alert is None
        if created:
            candidate = MedicalAlert(
                patient=measurement.patient,
                type=result.alert_type,
                niveau=result.severity,
                status=AlertStatus.OPEN,
                source=AlertSource.SYSTEM_RULE,
                rule_code=result.rule_code,
                rule_name=result.rule_name,
                message=result.message,
                source_type=source_type,
                source_id=measurement.pk,
                observed_value=result.observed_value,
                unit=result.unit,
                detected_at=measurement.date_mesure,
                metadata={**result.metadata, 'last_evaluated_at': evaluated_at, 'measurement_corrected': False},
            )
            candidate.full_clean()
            alert, created = MedicalAlert.objects.get_or_create(
                source_type=source_type,
                source_id=measurement.pk,
                rule_code=result.rule_code,
                defaults={
                    'patient': candidate.patient, 'type': candidate.type,
                    'niveau': candidate.niveau, 'status': candidate.status,
                    'source': candidate.source, 'rule_name': candidate.rule_name,
                    'message': candidate.message,
                    'observed_value': candidate.observed_value, 'unit': candidate.unit,
                    'detected_at': candidate.detected_at, 'metadata': candidate.metadata,
                },
            )
            if created:
                notify_alert_created(alert, actor=actor, request=request)
                _audit_alert(alert, action=AuditAction.CREATE, actor=actor, request=request)
            else:
                existing[result.rule_code] = alert
        else:
            alert.observed_value = result.observed_value
            alert.unit = result.unit
            alert.message = result.message
            alert.metadata = {
                **result.metadata,
                'last_evaluated_at': evaluated_at,
                'measurement_corrected': False,
            }
            alert.full_clean()
            alert.save(update_fields=('observed_value', 'unit', 'message', 'metadata', 'updated_at'))
        triggered.append(alert)

    for rule_code, alert in existing.items():
        if rule_code not in triggered_codes:
            alert.metadata = {
                **alert.metadata,
                'last_evaluated_at': evaluated_at,
                'measurement_corrected': True,
            }
            alert.full_clean()
            alert.save(update_fields=('metadata', 'updated_at'))
    return triggered


def _locked_authorized_alert(alert, doctor):
    if (
        not doctor.is_active
        or doctor.role != UserRole.DOCTOR
        or not doctor_can_access_patient(doctor, alert.patient.user)
    ):
        raise ValidationError('The doctor is not currently assigned to this patient.')
    return MedicalAlert.objects.select_for_update().select_related('patient__user').get(pk=alert.pk)


@transaction.atomic
def acknowledge_alert(alert, *, doctor, request=None):
    alert = _locked_authorized_alert(alert, doctor)
    if alert.status != AlertStatus.OPEN:
        raise ValidationError({'status': 'Only an open alert can be acknowledged.'})
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = timezone.now()
    alert.handled_by = doctor
    alert.full_clean()
    alert.save(update_fields=('status', 'acknowledged_at', 'handled_by', 'updated_at'))
    notify_alert_transition(alert, 'ACKNOWLEDGE', actor=doctor, request=request)
    _audit_alert(alert, action=AuditAction.UPDATE, actor=doctor, request=request, transition='ACKNOWLEDGE')
    return alert


@transaction.atomic
def resolve_alert(alert, *, doctor, reason='', request=None):
    alert = _locked_authorized_alert(alert, doctor)
    if alert.status != AlertStatus.ACKNOWLEDGED:
        raise ValidationError({'status': 'Only an acknowledged alert can be resolved.'})
    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = timezone.now()
    alert.handled_by = doctor
    alert.status_reason = reason.strip()
    alert.full_clean()
    alert.save(update_fields=('status', 'resolved_at', 'handled_by', 'status_reason', 'updated_at'))
    notify_alert_transition(alert, 'RESOLVE', actor=doctor, request=request)
    _audit_alert(alert, action=AuditAction.UPDATE, actor=doctor, request=request, transition='RESOLVE')
    return alert


@transaction.atomic
def dismiss_alert(alert, *, doctor, reason, request=None):
    alert = _locked_authorized_alert(alert, doctor)
    reason = reason.strip()
    if alert.status not in (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED):
        raise ValidationError({'status': 'Only an open or acknowledged alert can be dismissed.'})
    if not reason:
        raise ValidationError({'reason': 'A reason is required to dismiss an alert.'})
    alert.status = AlertStatus.DISMISSED
    alert.dismissed_at = timezone.now()
    alert.handled_by = doctor
    alert.status_reason = reason
    alert.full_clean()
    alert.save(update_fields=('status', 'dismissed_at', 'handled_by', 'status_reason', 'updated_at'))
    notify_alert_transition(alert, 'DISMISS', actor=doctor, request=request)
    _audit_alert(alert, action=AuditAction.UPDATE, actor=doctor, request=request, transition='DISMISS')
    return alert
