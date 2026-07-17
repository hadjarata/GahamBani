import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from accounts.tokens import VersionedRefreshToken
from alerts.models import AlertStatus, MedicalAlert
from alerts.services import acknowledge_alert, dismiss_alert, evaluate_measurement_for_alerts, resolve_alert
from medical_audit.models import AuditAction, AuditDomain, MedicalAuditEvent
from monitoring.models import BloodPressure
from profiles.models import DoctorProfile, PatientProfile
from profiles.services import assign_doctor_to_patient, end_doctor_patient_assignment

from .admin import NotificationAdmin
from .models import Notification, NotificationPriority, NotificationType
from .services import create_notification, notify_alert_created


def patient(email='notification-patient@example.com'):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.PATIENT)
    profile = PatientProfile.objects.create(user=user, date_naissance='1990-01-01', sexe='FEMALE', poids='65', taille='168')
    return user, profile


def doctor(email='notification-doctor@example.com', registration='NOTIF-MED-1'):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.DOCTOR)
    profile = DoctorProfile.objects.create(user=user, specialite='Médecine interne', numero_ordre=registration, hopital='Central', annees_experience=8)
    return user, profile


def auth(client, user):
    token = VersionedRefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')


def abnormal_pressure(profile, value=150):
    return BloodPressure.objects.create(patient=profile, systolique=value, diastolique=95, frequence_cardiaque=70, date_mesure=timezone.now())


def simple_notification(recipient, *, source_id=None, patient_profile=None, event=NotificationType.SYSTEM, **overrides):
    data = {
        'recipient': recipient, 'notification_type': event,
        'priority': NotificationPriority.NORMAL, 'title': 'Information',
        'message': 'Une information est disponible dans l’application.',
        'source_domain': 'SYSTEM', 'source_type': 'system.event',
        'source_id': source_id or uuid.uuid4(), 'event_code': event,
        'patient': patient_profile,
    }
    data.update(overrides)
    return create_notification(**data)


class NotificationModelTests(TestCase):
    def setUp(self):
        self.user, self.patient = patient()

    def test_valid_notification_is_unread_and_keeps_historical_references(self):
        notification = simple_notification(self.user, patient_profile=self.patient)
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)
        self.assertEqual(notification.recipient_reference, self.user.pk)
        self.assertEqual(notification.patient_reference, self.patient.pk)

    def test_recipient_is_required_for_new_notification(self):
        notification = Notification(
            recipient_reference=uuid.uuid4(), type=NotificationType.SYSTEM,
            priority=NotificationPriority.NORMAL, title='Titre', message='Message',
            source_domain='SYSTEM', source_type='system.event', source_id=uuid.uuid4(),
            event_code='SYSTEM',
        )
        with self.assertRaises(ValidationError):
            notification.full_clean()

    def test_read_state_is_enforced_in_python_and_database(self):
        notification = simple_notification(self.user)
        notification.is_read = True
        with self.assertRaises(ValidationError):
            notification.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notification.objects.filter(pk=notification.pk).update(is_read=True)

    def test_sql_and_service_idempotence(self):
        source_id = uuid.uuid4()
        first = simple_notification(self.user, source_id=source_id)
        second = simple_notification(self.user, source_id=source_id)
        self.assertEqual(first.pk, second.pk)
        duplicate = Notification.objects.get(pk=first.pk)
        duplicate.pk = uuid.uuid4()
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save(force_insert=True)

    def test_user_deletion_sets_null_without_losing_history(self):
        standalone = User.objects.create_user(email='deletable-notification@example.com', password='x', role=UserRole.DOCTOR)
        notification = simple_notification(standalone)
        standalone.delete()
        notification.refresh_from_db()
        self.assertIsNone(notification.recipient)
        self.assertIsNotNone(notification.recipient_reference)

    def test_metadata_sanitizer_removes_secrets_and_private_identifiers(self):
        notification = simple_notification(
            self.user,
            metadata={'token': 'secret-token', 'file_path': 'C:/private/file', 'safe_code': 'OK'},
            public_metadata={'alert_id': str(uuid.uuid4()), 'patient_email': 'private@example.com', 'exact_glucose': '342'},
        )
        serialized = json.dumps({'internal': notification.metadata, 'public': notification.public_metadata}).lower()
        self.assertNotIn('secret-token', serialized)
        self.assertNotIn('private@example.com', serialized)
        self.assertNotIn('c:/private', serialized)
        self.assertNotIn('342', serialized)
        self.assertIn('safe_code', serialized)


class AlertNotificationIntegrationTests(TestCase):
    def setUp(self):
        self.patient_user, self.patient = patient('integrated-notification-patient@example.com')
        self.doctor1, _ = doctor('doctor-one-notification@example.com', 'NOTIF-MED-2')
        self.doctor2, _ = doctor('doctor-two-notification@example.com', 'NOTIF-MED-3')
        self.unassigned, _ = doctor('unassigned-notification@example.com', 'NOTIF-MED-4')
        self.ended_doctor, _ = doctor('ended-notification@example.com', 'NOTIF-MED-5')
        self.inactive_doctor, _ = doctor('inactive-notification@example.com', 'NOTIF-MED-6')
        assign_doctor_to_patient(doctor_user=self.doctor1, patient_user=self.patient_user)
        assign_doctor_to_patient(doctor_user=self.doctor2, patient_user=self.patient_user)
        ended = assign_doctor_to_patient(doctor_user=self.ended_doctor, patient_user=self.patient_user)
        end_doctor_patient_assignment(ended)
        assign_doctor_to_patient(doctor_user=self.inactive_doctor, patient_user=self.patient_user)
        self.inactive_doctor.is_active = False
        self.inactive_doctor.save(update_fields=('is_active',))

    def test_created_alert_notifies_patient_and_each_current_active_doctor(self):
        alert = evaluate_measurement_for_alerts(abnormal_pressure(self.patient), actor=self.patient_user)[0]
        recipients = set(Notification.objects.filter(source_id=alert.pk).values_list('recipient_id', flat=True))
        self.assertEqual(recipients, {self.patient_user.pk, self.doctor1.pk, self.doctor2.pk})
        self.assertNotIn(self.unassigned.pk, recipients)
        self.assertNotIn(self.ended_doctor.pk, recipients)
        self.assertNotIn(self.inactive_doctor.pk, recipients)

    def test_reevaluation_does_not_duplicate_notifications(self):
        measurement = abnormal_pressure(self.patient)
        alert = evaluate_measurement_for_alerts(measurement)[0]
        initial = Notification.objects.filter(source_id=alert.pk).count()
        evaluate_measurement_for_alerts(measurement)
        self.assertEqual(Notification.objects.filter(source_id=alert.pk).count(), initial)

    def test_alert_deletion_never_deletes_notification_history(self):
        alert = evaluate_measurement_for_alerts(abnormal_pressure(self.patient))[0]
        notification_ids = list(Notification.objects.filter(source_id=alert.pk).values_list('pk', flat=True))
        alert.delete()
        self.assertEqual(Notification.objects.filter(pk__in=notification_ids).count(), len(notification_ids))

    def test_normal_measurement_creates_neither_alert_nor_notification(self):
        measurement = BloodPressure.objects.create(patient=self.patient, systolique=120, diastolique=80, date_mesure=timezone.now())
        self.assertEqual(evaluate_measurement_for_alerts(measurement), [])
        self.assertFalse(MedicalAlert.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_inactive_patient_receives_nothing(self):
        measurement = abnormal_pressure(self.patient, 151)
        self.patient_user.is_active = False
        self.patient_user.save(update_fields=('is_active',))
        alert = evaluate_measurement_for_alerts(measurement)[0]
        self.assertFalse(Notification.objects.filter(source_id=alert.pk).exists())

    def test_transitions_notify_only_patient_with_neutral_content(self):
        alert = evaluate_measurement_for_alerts(abnormal_pressure(self.patient))[0]
        Notification.objects.filter(source_id=alert.pk).delete()
        acknowledge_alert(alert, doctor=self.doctor1)
        resolve_alert(alert, doctor=self.doctor1, reason='Motif médical interne très sensible')
        notifications = Notification.objects.filter(source_id=alert.pk).order_by('created_at')
        self.assertEqual(list(notifications.values_list('recipient_id', flat=True)), [self.patient_user.pk, self.patient_user.pk])
        serialized = json.dumps(list(notifications.values('message', 'public_metadata')), ensure_ascii=False)
        self.assertNotIn('Motif médical interne', serialized)

    def test_dismiss_notifies_patient_and_invalid_transition_creates_nothing(self):
        alert = evaluate_measurement_for_alerts(abnormal_pressure(self.patient))[0]
        Notification.objects.filter(source_id=alert.pk).delete()
        dismiss_alert(alert, doctor=self.doctor1, reason='Artefact interne')
        self.assertEqual(Notification.objects.get().type, NotificationType.ALERT_DISMISSED)
        before = Notification.objects.count()
        with self.assertRaises(ValidationError):
            dismiss_alert(alert, doctor=self.doctor1, reason='Encore')
        self.assertEqual(Notification.objects.count(), before)

    def test_notification_failure_rolls_back_alert_and_transition(self):
        measurement = abnormal_pressure(self.patient)
        with patch('alerts.services.notify_alert_created', side_effect=RuntimeError('notification database failure')):
            with self.assertRaises(RuntimeError):
                evaluate_measurement_for_alerts(measurement)
        self.assertFalse(MedicalAlert.objects.exists())

        alert = evaluate_measurement_for_alerts(measurement)[0]
        with patch('alerts.services.notify_alert_transition', side_effect=RuntimeError('notification failure')):
            with self.assertRaises(RuntimeError):
                acknowledge_alert(alert, doctor=self.doctor1)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.OPEN)

    def test_notification_creation_is_audited_without_message(self):
        alert = evaluate_measurement_for_alerts(abnormal_pressure(self.patient))[0]
        events = MedicalAuditEvent.objects.filter(domain=AuditDomain.NOTIFICATIONS, action=AuditAction.CREATE)
        self.assertEqual(events.count(), 3)
        serialized = json.dumps(list(events.values('metadata')), ensure_ascii=False)
        self.assertNotIn(Notification.objects.filter(source_id=alert.pk).first().message, serialized)


class NotificationAPITests(APITestCase):
    def setUp(self):
        self.user, self.patient = patient('notification-api-patient@example.com')
        self.other_user, self.other_patient = patient('notification-api-other@example.com')
        self.notification = simple_notification(self.user, patient_profile=self.patient)
        self.other_notification = simple_notification(self.other_user, patient_profile=self.other_patient)
        auth(self.client, self.user)

    def test_list_detail_and_serializer_never_leak_other_or_internal_data(self):
        listed = self.client.get(reverse('notification-list'))
        own = self.client.get(reverse('notification-detail', args=[self.notification.pk]))
        other = self.client.get(reverse('notification-detail', args=[self.other_notification.pk]))
        self.assertEqual(listed.data['count'], 1)
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(other.status_code, status.HTTP_404_NOT_FOUND)
        for forbidden in ('recipient', 'recipient_reference', 'patient', 'public_metadata'):
            self.assertNotIn(forbidden, own.data)

    def test_mark_read_is_idempotent_and_updates_count_with_audit(self):
        count_url = reverse('notification-unread-count')
        self.assertEqual(self.client.get(count_url).data['unread_count'], 1)
        url = reverse('notification-read', args=[self.notification.pk])
        first = self.client.patch(url, format='json')
        read_at = first.data['read_at']
        second = self.client.patch(url, format='json')
        self.assertTrue(first.data['is_read'])
        self.assertEqual(second.data['read_at'], read_at)
        self.assertEqual(self.client.get(count_url).data['unread_count'], 0)
        events = MedicalAuditEvent.objects.filter(domain=AuditDomain.NOTIFICATIONS, action=AuditAction.UPDATE, metadata__operation='MARK_AS_READ')
        self.assertEqual(events.count(), 1)

    def test_other_user_cannot_read_notification(self):
        url = reverse('notification-read', args=[self.other_notification.pk])
        self.assertEqual(self.client.patch(url, format='json').status_code, status.HTTP_404_NOT_FOUND)

    def test_read_all_uses_owner_scope_and_is_idempotent(self):
        simple_notification(self.user)
        response = self.client.patch(reverse('notification-read-all'), format='json')
        again = self.client.patch(reverse('notification-read-all'), format='json')
        self.assertEqual(response.data['updated_count'], 2)
        self.assertEqual(again.data['updated_count'], 0)
        self.assertFalse(Notification.objects.filter(recipient=self.user, is_read=False).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.other_user, is_read=False).exists())
        self.assertEqual(MedicalAuditEvent.objects.filter(domain=AuditDomain.NOTIFICATIONS, metadata__operation='MARK_ALL_AS_READ').count(), 2)

    def test_authentication_inactive_and_admin_are_denied(self):
        self.client.credentials()
        self.assertEqual(self.client.get(reverse('notification-list')).status_code, status.HTTP_401_UNAUTHORIZED)
        auth(self.client, self.user)
        self.user.is_active = False
        self.user.save(update_fields=('is_active',))
        self.assertIn(self.client.get(reverse('notification-list')).status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        admin_user = User.objects.create_superuser('notification-admin@example.com', 'SafePassword2026!')
        auth(self.client, admin_user)
        self.assertEqual(self.client.get(reverse('notification-list')).status_code, status.HTTP_403_FORBIDDEN)

    def test_filters_pagination_dates_ordering_and_invalid_values(self):
        url = reverse('notification-list')
        ok = self.client.get(url, {'is_read': 'false', 'type': 'SYSTEM', 'priority': 'NORMAL', 'date_from': (timezone.now() - timedelta(days=1)).date().isoformat(), 'ordering': '-created_at', 'page_size': 1})
        invalid = self.client.get(url, {'is_read': 'maybe'})
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.data['count'], 1)
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_forbidden_methods_are_405(self):
        detail = reverse('notification-detail', args=[self.notification.pk])
        self.assertEqual(self.client.post(reverse('notification-list'), {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.put(detail, {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(detail).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.patch(detail, {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_detail_read_and_read_all_audits_exclude_message(self):
        self.client.get(reverse('notification-detail', args=[self.notification.pk]))
        self.client.patch(reverse('notification-read-all'), format='json')
        serialized = json.dumps(list(MedicalAuditEvent.objects.filter(domain=AuditDomain.NOTIFICATIONS).values('metadata')), ensure_ascii=False)
        self.assertNotIn(self.notification.message, serialized)

    def test_openapi_routes_filters_actions_and_errors(self):
        schema = self.client.get(reverse('schema'), HTTP_ACCEPT='application/vnd.oai.openapi+json').data
        paths = schema['paths']
        for path in ('/api/notifications/', '/api/notifications/{id}/read/', '/api/notifications/read-all/', '/api/notifications/unread-count/'):
            self.assertIn(path, paths)
        parameters = {item['name'] for item in paths['/api/notifications/']['get']['parameters']}
        self.assertTrue({'is_read', 'type', 'priority', 'date_from', 'date_to', 'ordering'}.issubset(parameters))
        for code in ('400', '401', '403', '404', '405'):
            self.assertIn(code, paths['/api/notifications/{id}/read/']['patch']['responses'])


class NotificationAdminTests(TestCase):
    def test_admin_is_read_only(self):
        model_admin = NotificationAdmin(Notification, admin.site)
        request = RequestFactory().get('/admin/notifications/notification/')
        request.user = User.objects.create_superuser('notification-admin-test@example.com', 'SafePassword2026!')
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertIsNone(model_admin.actions)
