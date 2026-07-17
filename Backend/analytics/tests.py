from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from accounts.tokens import VersionedRefreshToken
from alerts.models import AlertLevel, AlertSource, AlertStatus, AlertType, MedicalAlert
from medical_audit.models import AuditDomain, MedicalAuditEvent
from monitoring.models import BloodGlucose, BloodPressure, GlucoseUnit, MealContext
from profiles.models import DoctorProfile, PatientProfile
from profiles.services import assign_doctor_to_patient, end_doctor_patient_assignment


def patient(email='analytics-patient@example.com', active=True):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.PATIENT, is_active=active)
    profile = PatientProfile.objects.create(user=user, date_naissance='1990-01-01', sexe='FEMALE', poids='65', taille='168')
    return user, profile


def doctor(email='analytics-doctor@example.com', registration='AN-MED-1', active=True, profile=True):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.DOCTOR, is_active=active)
    doctor_profile = None
    if profile:
        doctor_profile = DoctorProfile.objects.create(user=user, specialite='Médecine', numero_ordre=registration, hopital='Central', annees_experience=8)
    return user, doctor_profile


def auth(client, user):
    token = VersionedRefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')


def pressure(profile, at, systolic=120, diastolic=80, heart_rate=70):
    return BloodPressure.objects.create(patient=profile, systolique=systolic, diastolique=diastolic, frequence_cardiaque=heart_rate, date_mesure=at)


def glucose(profile, at, value='100', unit=GlucoseUnit.MG_PER_DL, hba1c=None, context=MealContext.BEFORE_MEAL):
    return BloodGlucose.objects.create(patient=profile, valeur=value, unite=unit, hba1c=hba1c, contexte_repas=context, date_mesure=at)


def alert(profile, at, status_value=AlertStatus.OPEN, level=AlertLevel.HIGH, code='RULE_A'):
    values = {}
    if status_value == AlertStatus.ACKNOWLEDGED:
        values.update(acknowledged_at=at, handled_by=profile.user)
    elif status_value == AlertStatus.RESOLVED:
        values.update(acknowledged_at=at, resolved_at=at, handled_by=profile.user)
    elif status_value == AlertStatus.DISMISSED:
        values.update(dismissed_at=at, handled_by=profile.user, status_reason='Test')
    return MedicalAlert.objects.create(
        patient=profile, type=AlertType.GENERAL, niveau=level, status=status_value,
        source=AlertSource.SYSTEM_RULE, rule_code=code, rule_name=code,
        message='Message médical qui ne doit pas sortir', source_type='test', detected_at=at,
        **values,
    )


class AnalyticsAccessAndParametersTests(APITestCase):
    def setUp(self):
        self.user, self.profile = patient()
        self.other_user, self.other = patient('analytics-other@example.com')
        self.doctor, _ = doctor()
        self.assignment = assign_doctor_to_patient(doctor_user=self.doctor, patient_user=self.user)
        self.url = reverse('analytics:summary')

    def test_patient_reads_only_self_and_cannot_choose_patient(self):
        auth(self.client, self.user)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)
        response = self.client.get(self.url, {'patient_id': self.other.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_doctor_requires_current_assignment_and_masks_other_patient(self):
        auth(self.client, self.doctor)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.get(self.url, {'patient_id': self.profile.pk}).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(self.url, {'patient_id': self.other.pk}).status_code, status.HTTP_404_NOT_FOUND)
        end_doctor_patient_assignment(self.assignment)
        self.assertEqual(self.client.get(self.url, {'patient_id': self.profile.pk}).status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_profiles_inactive_users_and_admin_are_refused(self):
        no_profile = User.objects.create_user(email='no-profile@example.com', password='x', role=UserRole.PATIENT)
        auth(self.client, no_profile)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        admin = User.objects.create_user(email='admin-an@example.com', password='x', role=UserRole.ADMIN)
        auth(self.client, admin)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        inactive, _ = patient('inactive-an@example.com', active=False)
        auth(self.client, inactive)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_doctor_without_profile_inactive_doctor_and_inactive_patient_are_refused(self):
        no_profile, _ = doctor('doctor-no-profile@example.com', profile=False)
        auth(self.client, no_profile)
        self.assertEqual(self.client.get(self.url, {'patient_id': self.profile.pk}).status_code, 403)
        inactive_doctor, _ = doctor('inactive-doctor@example.com', 'AN-INACTIVE', active=False)
        auth(self.client, inactive_doctor)
        self.assertEqual(self.client.get(self.url, {'patient_id': self.profile.pk}).status_code, 401)
        inactive_patient_user, inactive_patient = patient('inactive-target@example.com', active=False)
        auth(self.client, self.doctor)
        self.assertEqual(self.client.get(self.url, {'patient_id': inactive_patient.pk}).status_code, 404)

    def test_period_validation(self):
        auth(self.client, self.user)
        cases = [
            {'period': 'unknown'},
            {'period': 'custom', 'date_from': '2026-01-01'},
            {'date_from': 'invalid', 'date_to': '2026-01-01'},
            {'date_from': '2026-02-01', 'date_to': '2026-01-01'},
            {'date_from': '2024-01-01', 'date_to': '2026-01-01'},
            {'period': '7d', 'date_from': '2026-01-01', 'date_to': '2026-01-02'},
        ]
        for params in cases:
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.url, params).status_code, status.HTTP_400_BAD_REQUEST)

    def test_series_parameter_validation_and_read_only_methods(self):
        auth(self.client, self.user)
        series_url = reverse('analytics:blood-pressure')
        self.assertEqual(self.client.get(series_url, {'granularity': 'hour'}).status_code, 400)
        self.assertEqual(self.client.get(series_url, {'granularity': 'day', 'page_size': 2}).status_code, 400)
        for route in ('summary', 'blood-pressure', 'blood-glucose', 'hba1c', 'alerts', 'trends'):
            url = reverse(f'analytics:{route}')
            for method in ('post', 'put', 'patch', 'delete'):
                self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 405)


class AnalyticsCalculationTests(APITestCase):
    def setUp(self):
        self.user, self.profile = patient('calculation@example.com')
        auth(self.client, self.user)
        self.now = timezone.now() - timedelta(minutes=1)

    def test_empty_and_populated_summary_with_latest_values(self):
        empty = self.client.get(reverse('analytics:summary')).data
        self.assertIsNone(empty['latest_blood_pressure'])
        self.assertEqual(empty['measurement_counts'], {'blood_pressure': 0, 'blood_glucose': 0})
        pressure(self.profile, self.now - timedelta(days=2), 120, 80, None)
        pressure(self.profile, self.now, 140, 90, 80)
        glucose(self.profile, self.now - timedelta(days=1), '1.00', GlucoseUnit.G_PER_L, '6.50')
        alert(self.profile, self.now, AlertStatus.OPEN, AlertLevel.CRITICAL)
        data = self.client.get(reverse('analytics:summary')).data
        self.assertEqual(data['latest_blood_pressure']['systolic'], 140)
        self.assertEqual(Decimal(data['latest_glucose']['value']), Decimal('100'))
        self.assertEqual(data['latest_hba1c']['unit'], '%')
        self.assertEqual(data['measurement_counts']['blood_pressure'], 2)
        self.assertEqual(data['averages']['systolic'], 130.0)
        self.assertEqual(data['alerts']['open'], 1)

    def test_summary_service_has_a_constant_query_count(self):
        from analytics.services import calculate_summary

        with self.assertNumQueries(6):
            calculate_summary(patient=self.profile, date_from=self.now - timedelta(days=30), date_to=self.now)

    def test_pressure_raw_daily_weekly_monthly_and_missing_heart_rate(self):
        pressure(self.profile, self.now - timedelta(days=1), 120, 80, None)
        pressure(self.profile, self.now, 140, 90, 80)
        url = reverse('analytics:blood-pressure')
        raw = self.client.get(url).data
        self.assertEqual(raw['count'], 2)
        self.assertEqual(raw['results'][0]['systolic'], 120.0)
        for granularity in ('day', 'week', 'month'):
            data = self.client.get(url, {'granularity': granularity}).data
            self.assertTrue(data['results'])
            self.assertEqual(sum(row['count'] for row in data['results']), 2)
        daily = self.client.get(url, {'granularity': 'day'}).data['results'][-1]
        self.assertEqual(daily['systolic_avg'], 140.0)

    def test_glucose_conversion_mixed_aggregation_and_context(self):
        glucose(self.profile, self.now - timedelta(hours=2), '1.00', GlucoseUnit.G_PER_L, context=MealContext.BEFORE_MEAL)
        glucose(self.profile, self.now - timedelta(hours=1), '200', GlucoseUnit.MG_PER_DL, context=MealContext.AFTER_MEAL)
        url = reverse('analytics:blood-glucose')
        raw = self.client.get(url).data
        self.assertEqual(raw['unit'], GlucoseUnit.MG_PER_DL)
        self.assertEqual([Decimal(str(row['value'])) for row in raw['results']], [Decimal('100.0'), Decimal('200.0')])
        aggregate = self.client.get(url, {'granularity': 'day'}).data['results'][0]
        self.assertEqual(Decimal(str(aggregate['average'])), Decimal('150.0'))
        filtered = self.client.get(url, {'context': MealContext.AFTER_MEAL}).data
        self.assertEqual(filtered['count'], 1)

    def test_hba1c_order_and_point_trends(self):
        url = reverse('analytics:hba1c')
        self.assertEqual(self.client.get(url).data['results'], [])
        glucose(self.profile, self.now - timedelta(days=2), '100', hba1c='7.00')
        glucose(self.profile, self.now - timedelta(days=1), '100', hba1c='7.50')
        glucose(self.profile, self.now, '100', hba1c='7.00')
        data = self.client.get(url).data['results']
        self.assertEqual([row['trend'] for row in data], ['INSUFFICIENT_DATA', 'UP', 'DOWN'])

    def test_alert_distributions_evolution_and_no_message_leak(self):
        alert(self.profile, self.now - timedelta(days=1), AlertStatus.OPEN, AlertLevel.HIGH, 'A')
        alert(self.profile, self.now, AlertStatus.ACKNOWLEDGED, AlertLevel.LOW, 'B')
        alert(self.profile, self.now, AlertStatus.RESOLVED, AlertLevel.MEDIUM, 'C')
        alert(self.profile, self.now, AlertStatus.DISMISSED, AlertLevel.INFO, 'D')
        _, other = patient('alert-leak@example.com')
        alert(other, self.now, AlertStatus.OPEN, AlertLevel.CRITICAL, 'SECRET')
        response = self.client.get(reverse('analytics:alerts'))
        self.assertEqual(response.data['total'], 4)
        self.assertEqual(response.data['by_status']['OPEN'], 1)
        self.assertEqual(response.data['by_status']['ACKNOWLEDGED'], 1)
        self.assertEqual(response.data['by_status']['RESOLVED'], 1)
        self.assertEqual(response.data['by_status']['DISMISSED'], 1)
        self.assertNotIn('SECRET', response.data['by_rule_code'])
        self.assertNotIn('Message médical', str(response.data))

    def test_raw_pagination_is_bounded_and_order_configurable(self):
        for index in range(105):
            pressure(self.profile, self.now - timedelta(minutes=index), 120, 80)
        url = reverse('analytics:blood-pressure')
        data = self.client.get(url, {'page_size': 100, 'ordering': 'desc'}).data
        self.assertEqual(data['count'], 105)
        self.assertEqual(len(data['results']), 100)
        self.assertIsNotNone(data['next'])
        self.assertEqual(self.client.get(url, {'page_size': 101}).status_code, 400)


class AnalyticsTrendAuditSchemaTests(APITestCase):
    def setUp(self):
        self.user, self.profile = patient('trend@example.com')
        auth(self.client, self.user)
        self.end = timezone.now() - timedelta(minutes=1)

    def add_window_pressures(self, previous, current):
        for days, value in ((10, previous), (9, previous), (3, current), (2, current)):
            pressure(self.profile, self.end - timedelta(days=days), value, value - 40, 70)

    def test_trend_up_down_stable_and_insufficient(self):
        url = reverse('analytics:trends')
        self.add_window_pressures(120, 140)
        self.assertEqual(self.client.get(url).data['indicators']['systolic']['direction'], 'UP')
        BloodPressure.objects.all().delete()
        self.add_window_pressures(140, 120)
        self.assertEqual(self.client.get(url).data['indicators']['systolic']['direction'], 'DOWN')
        BloodPressure.objects.all().delete()
        self.add_window_pressures(120, 120)
        self.assertEqual(self.client.get(url).data['indicators']['systolic']['direction'], 'STABLE')
        BloodPressure.objects.all().delete()
        pressure(self.profile, self.end - timedelta(days=2), 120, 80)
        self.assertEqual(self.client.get(url).data['indicators']['systolic']['direction'], 'INSUFFICIENT_DATA')

    @override_settings(ANALYTICS_TREND_STABLE_THRESHOLD='5')
    def test_configurable_stability_threshold(self):
        self.add_window_pressures(120, 124)
        data = self.client.get(reverse('analytics:trends')).data
        self.assertEqual(data['indicators']['systolic']['direction'], 'STABLE')

    def test_zero_previous_average_omits_percentage(self):
        # Unit-level behavior is relevant because valid medical model ranges cannot be zero.
        from analytics.services import _trend
        result = _trend({'count': 2, 'average': 1}, {'count': 2, 'average': 0}, minimum=2, stable_threshold=Decimal('0'))
        self.assertIsNone(result['percentage_change'])

    def test_each_successful_request_is_minimally_audited(self):
        self.client.get(reverse('analytics:blood-pressure'), {'period': '7d'})
        event = MedicalAuditEvent.objects.get(domain=AuditDomain.ANALYTICS)
        self.assertEqual(event.patient_id, self.profile.pk)
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.metadata['statistic_type'], 'BLOOD_PRESSURE')
        self.assertNotIn('results', event.metadata)
        self.assertNotIn('systolic', str(event.metadata).lower())

    def test_doctor_is_the_audit_actor_for_assigned_patient(self):
        doctor_user, _ = doctor('audit-doctor@example.com', 'AUDIT-AN-1')
        assign_doctor_to_patient(doctor_user=doctor_user, patient_user=self.user)
        auth(self.client, doctor_user)
        self.client.get(reverse('analytics:summary'), {'patient_id': self.profile.pk})
        event = MedicalAuditEvent.objects.get(domain=AuditDomain.ANALYTICS)
        self.assertEqual(event.actor_id, doctor_user.pk)
        self.assertEqual(event.patient_id, self.profile.pk)

    def test_all_routes_are_present_in_openapi(self):
        response = self.client.get(reverse('schema'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for route in ('summary', 'blood-pressure', 'blood-glucose', 'hba1c', 'alerts', 'trends'):
            self.assertIn(f'/api/analytics/{route}/', content)
        self.assertIn('granularity', content)
