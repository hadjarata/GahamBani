from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from accounts.tokens import VersionedRefreshToken
from medical_audit.models import AuditAction, AuditDomain, MedicalAuditEvent
from monitoring.models import BloodGlucose, BloodPressure, GlucoseUnit
from profiles.models import DoctorProfile, PatientProfile
from profiles.services import assign_doctor_to_patient, end_doctor_patient_assignment

from .models import AlertLevel, AlertStatus, MedicalAlert
from .admin import MedicalAlertAdmin
from .rules import RULES, glucose_to_mg_dl, rules_for_measurement
from .services import acknowledge_alert, dismiss_alert, evaluate_measurement_for_alerts, resolve_alert


def patient(email='alert-patient@example.com', *, active=True):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.PATIENT, is_active=active)
    profile = PatientProfile.objects.create(user=user, date_naissance='1990-01-01', sexe='FEMALE', poids='65', taille='168')
    return user, profile


def doctor(email='alert-doctor@example.com', registration='ALERT-MED-1', *, active=True):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.DOCTOR, is_active=active)
    profile = DoctorProfile.objects.create(user=user, specialite='Médecine interne', numero_ordre=registration, hopital='Central', annees_experience=8)
    return user, profile


def auth(client, user):
    token = VersionedRefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')


def pressure(profile, systolic=120, diastolic=80, heart_rate=70):
    return BloodPressure.objects.create(patient=profile, systolique=systolic, diastolique=diastolic, frequence_cardiaque=heart_rate, date_mesure=timezone.now())


def glucose(profile, value='1.10', unit=GlucoseUnit.G_PER_L, hba1c=None):
    return BloodGlucose.objects.create(patient=profile, valeur=value, unite=unit, hba1c=hba1c, date_mesure=timezone.now())


def results(measurement):
    return {rule.code: rule.evaluate(measurement) for rule in rules_for_measurement(measurement)}


class AlertRuleTests(TestCase):
    def setUp(self):
        _, self.patient = patient()

    def test_normal_pressure_and_missing_heart_rate_trigger_nothing(self):
        measurement = pressure(self.patient, 120, 80, None)
        self.assertFalse(any(results(measurement).values()))

    def test_pressure_boundaries_are_inclusive_and_explain_parameters(self):
        low = pressure(self.patient, 90, 60)
        elevated = pressure(self.patient, 140, 90)
        very_high = pressure(self.patient, 180, 119)
        combination = pressure(self.patient, 180, 120)
        self.assertIsNotNone(results(low)['BP_VERY_LOW'])
        self.assertIsNotNone(results(elevated)['BP_ELEVATED'])
        self.assertIsNotNone(results(very_high)['BP_VERY_HIGH'])
        combo_results = results(combination)
        self.assertIsNotNone(combo_results['BP_VERY_HIGH'])
        self.assertIsNotNone(combo_results['BP_CRITICAL_COMBINATION'])
        self.assertEqual(combo_results['BP_CRITICAL_COMBINATION'].metadata['triggered_parameters'], ['systolique', 'diastolique'])

    def test_values_just_inside_pressure_limits_do_not_trigger(self):
        measurement = pressure(self.patient, 139, 89, 41)
        self.assertFalse(any(results(measurement).values()))

    def test_heart_rate_absent_low_high_and_multiple_rules(self):
        self.assertIsNone(results(pressure(self.patient, 120, 80, None))['HR_LOW'])
        self.assertIsNotNone(results(pressure(self.patient, 120, 80, 40))['HR_LOW'])
        multiple = results(pressure(self.patient, 180, 120, 130))
        self.assertIsNotNone(multiple['HR_HIGH'])
        self.assertGreaterEqual(sum(value is not None for value in multiple.values()), 3)

    def test_glucose_conversion_is_explicit_exact_and_non_mutating(self):
        self.assertEqual(glucose_to_mg_dl(Decimal('1.80'), GlucoseUnit.G_PER_L), Decimal('180.00'))
        self.assertEqual(glucose_to_mg_dl(Decimal('180'), GlucoseUnit.MG_PER_DL), Decimal('180'))
        measurement = glucose(self.patient, '1.80', GlucoseUnit.G_PER_L)
        results(measurement)
        measurement.refresh_from_db()
        self.assertEqual(measurement.valeur, Decimal('1.80'))
        self.assertEqual(measurement.unite, GlucoseUnit.G_PER_L)

    def test_glucose_normal_limits_and_both_units(self):
        normal = glucose(self.patient, '1.79', GlucoseUnit.G_PER_L)
        high_g = glucose(self.patient, '1.80', GlucoseUnit.G_PER_L)
        high_mg = glucose(self.patient, '180', GlucoseUnit.MG_PER_DL)
        very_low = glucose(self.patient, '54', GlucoseUnit.MG_PER_DL)
        very_high = glucose(self.patient, '2.50', GlucoseUnit.G_PER_L)
        self.assertFalse(any(results(normal).values()))
        self.assertIsNotNone(results(high_g)['GLUCOSE_HIGH'])
        self.assertIsNotNone(results(high_mg)['GLUCOSE_HIGH'])
        self.assertIsNotNone(results(very_low)['GLUCOSE_VERY_LOW'])
        self.assertIsNotNone(results(very_high)['GLUCOSE_VERY_HIGH'])

    def test_hba1c_absent_normal_and_boundary(self):
        self.assertIsNone(results(glucose(self.patient, '1.10', hba1c=None))['HBA1C_HIGH'])
        self.assertIsNone(results(glucose(self.patient, '1.10', hba1c='7.99'))['HBA1C_HIGH'])
        self.assertIsNotNone(results(glucose(self.patient, '1.10', hba1c='8.00'))['HBA1C_HIGH'])

    @override_settings(ALERT_RULE_THRESHOLDS={
        'blood_pressure': {'very_low_systolic': 95, 'very_low_diastolic': 65, 'elevated_systolic': 150, 'elevated_diastolic': 95, 'very_high_systolic': 190, 'very_high_diastolic': 125, 'critical_systolic': 190, 'critical_diastolic': 125},
        'heart_rate': {'low': 45, 'high': 125},
        'blood_glucose': {'very_low_mg_dl': 60, 'high_mg_dl': 170, 'very_high_mg_dl': 240, 'hba1c_high_percent': 7.5},
    })
    def test_thresholds_are_runtime_configurable(self):
        self.assertIsNotNone(results(pressure(self.patient, 149, 95))['BP_ELEVATED'])
        self.assertIsNotNone(results(glucose(self.patient, '1.70'))['GLUCOSE_HIGH'])


class AlertEngineAndStateTests(TestCase):
    def setUp(self):
        self.patient_user, self.patient = patient()
        self.doctor_user, _ = doctor()
        assign_doctor_to_patient(doctor_user=self.doctor_user, patient_user=self.patient_user)

    def test_normal_measurement_creates_no_alert(self):
        self.assertEqual(evaluate_measurement_for_alerts(pressure(self.patient)), [])
        self.assertFalse(MedicalAlert.objects.exists())

    def test_abnormal_measurement_can_create_multiple_explainable_alerts(self):
        measurement = pressure(self.patient, 180, 120, 130)
        alerts = evaluate_measurement_for_alerts(measurement, actor=self.patient_user)
        self.assertGreaterEqual(len(alerts), 3)
        for alert in alerts:
            self.assertEqual(alert.source_id, measurement.pk)
            self.assertEqual(alert.source_type, 'monitoring.bloodpressure')
            self.assertTrue(alert.rule_code)
            self.assertTrue(alert.observed_value)

    def test_evaluation_is_idempotent_and_database_enforced(self):
        measurement = pressure(self.patient, 150, 95)
        first = evaluate_measurement_for_alerts(measurement)
        second = evaluate_measurement_for_alerts(measurement)
        self.assertEqual([item.pk for item in first], [item.pk for item in second])
        self.assertEqual(MedicalAlert.objects.count(), 1)
        duplicate = MedicalAlert.objects.get(pk=first[0].pk)
        duplicate.pk = None
        duplicate._state.adding = True
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save(force_insert=True)

    def test_correction_marks_history_without_resolving_or_deleting(self):
        measurement = pressure(self.patient, 150, 95)
        alert = evaluate_measurement_for_alerts(measurement)[0]
        measurement.systolique = 120
        measurement.diastolique = 80
        measurement.save(update_fields=('systolique', 'diastolique', 'updated_at'))
        self.assertEqual(evaluate_measurement_for_alerts(measurement), [])
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.OPEN)
        self.assertTrue(alert.metadata['measurement_corrected'])

    def test_resolved_alert_is_never_reopened_by_reevaluation(self):
        measurement = pressure(self.patient, 150, 95)
        alert = evaluate_measurement_for_alerts(measurement)[0]
        acknowledge_alert(alert, doctor=self.doctor_user)
        resolve_alert(alert, doctor=self.doctor_user, reason='Prise en charge effectuée')
        evaluate_measurement_for_alerts(measurement)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.RESOLVED)

    def test_measurement_deletion_never_deletes_historical_alert(self):
        measurement = pressure(self.patient, 150, 95)
        alert = evaluate_measurement_for_alerts(measurement)[0]
        measurement.delete()
        self.assertTrue(MedicalAlert.objects.filter(pk=alert.pk).exists())

    def test_transition_state_machine_and_dismiss_reason(self):
        alert = evaluate_measurement_for_alerts(pressure(self.patient, 150, 95))[0]
        with self.assertRaises(ValidationError):
            resolve_alert(alert, doctor=self.doctor_user)
        acknowledged = acknowledge_alert(alert, doctor=self.doctor_user)
        with self.assertRaises(ValidationError):
            acknowledge_alert(acknowledged, doctor=self.doctor_user)
        resolved = resolve_alert(acknowledged, doctor=self.doctor_user, reason='Contrôle réalisé')
        self.assertEqual(resolved.status, AlertStatus.RESOLVED)
        with self.assertRaises(ValidationError):
            dismiss_alert(resolved, doctor=self.doctor_user, reason='x')

        other = evaluate_measurement_for_alerts(pressure(self.patient, 151, 96))[0]
        with self.assertRaises(ValidationError):
            dismiss_alert(other, doctor=self.doctor_user, reason=' ')
        self.assertEqual(dismiss_alert(other, doctor=self.doctor_user, reason='Artefact confirmé').status, AlertStatus.DISMISSED)


class AutomaticAlertIntegrationTests(APITestCase):
    def setUp(self):
        self.user, self.patient = patient()
        auth(self.client, self.user)

    def pressure_payload(self, systolic=120, diastolic=80, **extra):
        data = {'systolique': systolic, 'diastolique': diastolic, 'date_mesure': timezone.now().isoformat()}
        data.update(extra)
        return data

    def test_create_normal_none_abnormal_alert_and_audit_same_source(self):
        normal = self.client.post(reverse('blood-pressure-list'), self.pressure_payload(), format='json')
        abnormal = self.client.post(reverse('blood-pressure-list'), self.pressure_payload(150, 95), format='json')
        self.assertEqual(normal.status_code, status.HTTP_201_CREATED)
        self.assertEqual(abnormal.status_code, status.HTTP_201_CREATED)
        alert = MedicalAlert.objects.get()
        self.assertEqual(str(alert.source_id), abnormal.data['id'])
        audit = MedicalAuditEvent.objects.get(domain=AuditDomain.ALERTS, action=AuditAction.CREATE)
        self.assertEqual(audit.resource_id, alert.pk)
        self.assertEqual(audit.metadata['rule_code'], 'BP_ELEVATED')

    def test_glucose_abnormal_creates_alert_but_invalid_measurement_does_not(self):
        response = self.client.post(reverse('blood-glucose-list'), {'valeur': '2.50', 'unite': 'G_PER_L', 'date_mesure': timezone.now().isoformat()}, format='json')
        invalid = self.client.post(reverse('blood-glucose-list'), {'valeur': '100', 'unite': 'G_PER_L', 'date_mesure': timezone.now().isoformat()}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(MedicalAlert.objects.count(), 1)

    def test_patch_only_reevaluates_relevant_fields_and_preserves_history(self):
        created = self.client.post(reverse('blood-pressure-list'), self.pressure_payload(150, 95), format='json')
        alert = MedicalAlert.objects.get()
        evaluated_at = alert.metadata['last_evaluated_at']
        detail = reverse('blood-pressure-detail', args=[created.data['id']])
        notes = self.client.patch(detail, {'notes': 'contexte uniquement'}, format='json')
        alert.refresh_from_db()
        self.assertEqual(notes.status_code, status.HTTP_200_OK)
        self.assertEqual(alert.metadata['last_evaluated_at'], evaluated_at)
        corrected = self.client.patch(detail, {'systolique': 120, 'diastolique': 80}, format='json')
        alert.refresh_from_db()
        self.assertEqual(corrected.status_code, status.HTTP_200_OK)
        self.assertTrue(alert.metadata['measurement_corrected'])
        self.assertEqual(alert.status, AlertStatus.OPEN)

    def test_engine_programming_error_rolls_back_measurement(self):
        class BrokenRule:
            code = 'BROKEN'
            def evaluate(self, measurement):
                raise RuntimeError('programming error')
        self.client.raise_request_exception = False
        with patch('alerts.services.rules_for_measurement', return_value=(BrokenRule(),)):
            with self.assertLogs('django.request', level='ERROR'):
                response = self.client.post(reverse('blood-pressure-list'), self.pressure_payload(150, 95), format='json')
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertFalse(BloodPressure.objects.exists())
        self.assertFalse(MedicalAlert.objects.exists())


class AlertAPITests(APITestCase):
    def setUp(self):
        self.patient_user, self.patient = patient('api-alert-patient@example.com')
        self.other_user, self.other_patient = patient('api-other-patient@example.com')
        self.doctor_user, self.doctor = doctor('api-alert-doctor@example.com', 'ALERT-MED-API')
        self.assignment = assign_doctor_to_patient(doctor_user=self.doctor_user, patient_user=self.patient_user)
        self.alert = evaluate_measurement_for_alerts(pressure(self.patient, 150, 95))[0]
        self.other_alert = evaluate_measurement_for_alerts(pressure(self.other_patient, 151, 96))[0]

    def test_patient_lists_and_retrieves_only_own_without_transitions(self):
        auth(self.client, self.patient_user)
        listed = self.client.get(reverse('alert-list'))
        own = self.client.get(reverse('alert-detail', args=[self.alert.pk]))
        other = self.client.get(reverse('alert-detail', args=[self.other_alert.pk]))
        transition = self.client.patch(reverse('alert-acknowledge', args=[self.alert.pk]), {}, format='json')
        self.assertEqual(listed.data['count'], 1)
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(other.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(transition.status_code, status.HTTP_403_FORBIDDEN)

    def test_assigned_doctor_reads_acknowledges_resolves_and_audits(self):
        auth(self.client, self.doctor_user)
        self.assertEqual(self.client.get(reverse('alert-detail', args=[self.alert.pk])).status_code, status.HTTP_200_OK)
        acknowledged = self.client.patch(reverse('alert-acknowledge', args=[self.alert.pk]), {}, format='json')
        resolved = self.client.patch(reverse('alert-resolve', args=[self.alert.pk]), {'reason': 'Prise en charge'}, format='json')
        self.assertEqual(acknowledged.data['status'], AlertStatus.ACKNOWLEDGED)
        self.assertEqual(resolved.data['status'], AlertStatus.RESOLVED)
        transitions = MedicalAuditEvent.objects.filter(domain=AuditDomain.ALERTS, action=AuditAction.UPDATE)
        self.assertEqual(set(transitions.values_list('metadata__transition', flat=True)), {'ACKNOWLEDGE', 'RESOLVE'})

    def test_dismiss_requires_reason_and_is_audited_without_reason_text(self):
        auth(self.client, self.doctor_user)
        missing = self.client.patch(reverse('alert-dismiss', args=[self.alert.pk]), {}, format='json')
        reason = 'Artefact de mesure confirmé sans suite clinique'
        dismissed = self.client.patch(reverse('alert-dismiss', args=[self.alert.pk]), {'reason': reason}, format='json')
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(dismissed.data['status'], AlertStatus.DISMISSED)
        audit = MedicalAuditEvent.objects.filter(domain=AuditDomain.ALERTS, action=AuditAction.UPDATE).get()
        self.assertNotIn(reason, str(audit.metadata))
        self.assertEqual(audit.metadata['transition'], 'DISMISS')

    def test_unassigned_ended_inactive_and_admin_are_denied(self):
        unassigned, _ = doctor('unassigned-alert@example.com', 'ALERT-MED-X')
        auth(self.client, unassigned)
        self.assertEqual(self.client.get(reverse('alert-detail', args=[self.alert.pk])).status_code, status.HTTP_404_NOT_FOUND)
        end_doctor_patient_assignment(self.assignment)
        auth(self.client, self.doctor_user)
        self.assertEqual(self.client.get(reverse('alert-detail', args=[self.alert.pk])).status_code, status.HTTP_404_NOT_FOUND)
        self.doctor_user.is_active = False
        self.doctor_user.save(update_fields=('is_active',))
        self.assertIn(self.client.get(reverse('alert-list')).status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        admin_user = User.objects.create_superuser('alerts-admin@example.com', 'SafePassword2026!')
        auth(self.client, admin_user)
        self.assertEqual(self.client.get(reverse('alert-list')).status_code, status.HTTP_403_FORBIDDEN)

    def test_inactive_patient_alerts_are_hidden_from_doctor(self):
        auth(self.client, self.doctor_user)
        self.patient_user.is_active = False
        self.patient_user.save(update_fields=('is_active',))
        self.assertEqual(self.client.get(reverse('alert-list')).data['count'], 0)

    def test_filters_ordering_pagination_and_no_patient_leak(self):
        auth(self.client, self.doctor_user)
        url = reverse('alert-list')
        ok = self.client.get(url, {'status': 'OPEN', 'severity': 'HIGH', 'rule_code': 'BP_ELEVATED', 'patient_id': self.patient.pk, 'date_from': (timezone.now() - timedelta(days=1)).date().isoformat(), 'ordering': '-severity', 'page_size': 1})
        invalid = self.client.get(url, {'status': 'INVALID'})
        leak = self.client.get(url, {'patient_id': self.other_patient.pk})
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.data['count'], 1)
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(leak.data['count'], 0)

    def test_put_delete_and_generic_patch_are_disabled(self):
        auth(self.client, self.doctor_user)
        detail = reverse('alert-detail', args=[self.alert.pk])
        self.assertEqual(self.client.put(detail, {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(detail).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.patch(detail, {'status': 'RESOLVED'}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_openapi_documents_routes_actions_enums_and_errors(self):
        schema = self.client.get(reverse('schema'), HTTP_ACCEPT='application/vnd.oai.openapi+json').data
        paths = schema['paths']
        self.assertIn('/api/alerts/', paths)
        self.assertIn('/api/alerts/{id}/acknowledge/', paths)
        self.assertIn('/api/alerts/{id}/resolve/', paths)
        self.assertIn('/api/alerts/{id}/dismiss/', paths)
        self.assertNotIn('put', paths['/api/alerts/{id}/'])
        self.assertNotIn('delete', paths['/api/alerts/{id}/'])
        responses = paths['/api/alerts/{id}/acknowledge/']['patch']['responses']
        for code in ('400', '401', '403', '404', '405'):
            self.assertIn(code, responses)


class AlertAdminTests(TestCase):
    def test_admin_is_read_only_and_optimized(self):
        model_admin = MedicalAlertAdmin(MedicalAlert, admin.site)
        request = RequestFactory().get('/admin/alerts/medicalalert/')
        request.user = User.objects.create_superuser('alert-admin-test@example.com', 'SafePassword2026!')
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertIn('patient__user', model_admin.list_select_related)
        self.assertIn('source_id', model_admin.search_fields)
