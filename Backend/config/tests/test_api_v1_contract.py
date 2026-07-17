import tempfile
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from accounts.tokens import VersionedRefreshToken
from alerts.models import MedicalAlert
from api_contract import codes
from medical_records.models import Allergy, ChronicDisease, Consultation, MedicalRecord, Treatment
from monitoring.models import BloodGlucose, BloodPressure, GlucoseUnit
from notifications.models import Notification
from profiles.management.commands.seed_demo_data import DOCTOR_EMAIL, FORMER_DOCTOR_EMAIL, PATIENT_EMAIL
from profiles.models import DoctorProfile, PatientDoctorAssignment, PatientProfile


def patient(email='contract-patient@example.com', *, profile=True):
    user = User.objects.create_user(
        email=email, password='SafePassword2026!', role=UserRole.PATIENT,
        first_name='Contrat', last_name='Patient', phone='+22370000000',
    )
    patient_profile = None
    if profile:
        patient_profile = PatientProfile.objects.create(
            user=user, date_naissance='1990-01-01', sexe='OTHER', poids='70', taille='170',
        )
    return user, patient_profile


def authenticate(client, user):
    token = VersionedRefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')


class APIV1RoutingAndErrorTests(APITestCase):
    def setUp(self):
        self.user, self.profile = patient()

    def test_namespaced_routes_and_health_contract(self):
        self.assertEqual(reverse('api-v1:health'), '/api/v1/health/')
        self.assertEqual(reverse('api-v1:login'), '/api/v1/auth/login/')
        self.assertEqual(reverse('api-v1:profiles:me'), '/api/v1/profiles/me/')
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'status': 'ok', 'version': 'v1'})
        for forbidden in ('database', 'django', 'debug', 'environment', 'secret'):
            self.assertNotIn(forbidden, str(response.data).lower())

    def test_v1_authentication_validation_permission_and_method_errors(self):
        unauthenticated = self.client.get('/api/v1/profiles/me/')
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(unauthenticated.data['code'], codes.AUTHENTICATION_REQUIRED)

        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid-token')
        invalid = self.client.get('/api/v1/profiles/me/')
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid.data['code'], codes.INVALID_TOKEN)

        self.client.credentials()
        validation = self.client.post('/api/v1/auth/register/', {}, format='json')
        self.assertEqual(validation.status_code, 400)
        self.assertEqual(validation.data['code'], codes.VALIDATION_ERROR)
        self.assertIn('email', validation.data['errors'])

        authenticate(self.client, self.user)
        denied = self.client.get('/api/v1/profiles/my-patients/')
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data['code'], codes.PERMISSION_DENIED)

        method = self.client.post('/api/v1/health/', {}, format='json')
        self.assertEqual(method.status_code, 405)
        self.assertEqual(method.data['code'], codes.METHOD_NOT_ALLOWED)

    def test_profile_missing_has_stable_business_code(self):
        missing_user, _ = patient('contract-missing@example.com', profile=False)
        authenticate(self.client, missing_user)
        response = self.client.get('/api/v1/profiles/me/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['code'], codes.PROFILE_MISSING)

    def test_legacy_alias_keeps_old_error_shape_and_success_behavior(self):
        legacy_error = self.client.get('/api/profiles/me/')
        self.assertEqual(legacy_error.status_code, 401)
        self.assertNotIn('code', legacy_error.data)
        authenticate(self.client, self.user)
        legacy = self.client.get('/api/profiles/me/').data
        versioned = self.client.get('/api/v1/profiles/me/').data
        self.assertEqual(legacy, versioned)

    def test_pagination_uuid_and_utc_datetime_contract(self):
        measurement = BloodPressure.objects.create(
            patient=self.profile, systolique=120, diastolique=80,
            frequence_cardiaque=70, date_mesure=timezone.now(),
        )
        authenticate(self.client, self.user)
        response = self.client.get('/api/v1/monitoring/blood-pressure/')
        self.assertEqual(set(response.data), {'count', 'next', 'previous', 'results'})
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertIsInstance(row['id'], str)
        self.assertEqual(row['id'], str(measurement.pk))
        self.assertRegex(row['date_mesure'], r'(Z|[+-]\d\d:\d\d)$')


class OpenAPIV1SnapshotTests(TestCase):
    def schema(self):
        return yaml.safe_load((settings.BASE_DIR / 'openapi-v1.yaml').read_text(encoding='utf-8'))

    def test_snapshot_matches_generated_schema_structurally(self):
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / 'openapi.yaml'
            call_command(
                'spectacular', file=str(generated), verbosity=0,
            )
            self.assertEqual(self.schema(), yaml.safe_load(generated.read_text(encoding='utf-8')))

    def test_v1_schema_has_unique_operations_enums_security_and_error_contract(self):
        schema = self.schema()
        self.assertTrue(schema['paths'])
        self.assertTrue(all(path.startswith('/api/v1/') for path in schema['paths']))
        operation_ids = [
            operation['operationId']
            for path_item in schema['paths'].values()
            for method, operation in path_item.items()
            if method in {'get', 'post', 'put', 'patch', 'delete'}
        ]
        self.assertEqual(len(operation_ids), len(set(operation_ids)))
        self.assertIn('V1Error', schema['components']['schemas'])
        self.assertIn('jwtAuth', schema['components']['securitySchemes'])
        serialized = str(schema)
        for enum_value in ('PATIENT', 'DOCTOR', 'MG_PER_DL', 'ACKNOWLEDGED', 'MEDICAL_ALERT_CREATED', 'raw', '30d', 'ENDED', 'ORDONNANCE'):
            self.assertIn(enum_value, serialized)

    def test_v1_schema_endpoint_excludes_legacy_paths(self):
        response = self.client.get('/api/schema/v1/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('/api/v1/profiles/me/', content)
        self.assertNotIn('\n  /api/profiles/me/:', content)


class DemoSeedTests(TestCase):
    @override_settings(ALLOW_DEMO_DATA=True)
    def test_seed_is_safe_idempotent_and_uses_real_alert_pipeline(self):
        call_command('seed_demo_data', password='Demo-Test-Password-2026!', verbosity=0)
        first_counts = self.counts()
        call_command('seed_demo_data', password='Demo-Test-Password-2026!', verbosity=0)
        self.assertEqual(first_counts, self.counts())
        self.assertEqual(User.objects.filter(email__in=(PATIENT_EMAIL, DOCTOR_EMAIL, FORMER_DOCTOR_EMAIL)).count(), 3)
        self.assertTrue(all(user.email.endswith('.invalid') for user in User.objects.all()))
        self.assertTrue(all('DEMO' in f'{user.first_name} {user.last_name}' for user in User.objects.all()))
        self.assertGreater(MedicalAlert.objects.count(), 0)
        self.assertGreater(Notification.objects.count(), 0)
        self.assertTrue(User.objects.get(email=PATIENT_EMAIL).check_password('Demo-Test-Password-2026!'))

    @override_settings(ALLOW_DEMO_DATA=False)
    def test_seed_is_explicitly_refused_outside_development(self):
        with self.assertRaisesMessage(CommandError, 'interdit hors environnement'):
            call_command('seed_demo_data', password='Demo-Test-Password-2026!', verbosity=0)
        self.assertEqual(User.objects.count(), 0)

    def counts(self):
        return {
            'users': User.objects.count(), 'patients': PatientProfile.objects.count(),
            'doctors': DoctorProfile.objects.count(), 'assignments': PatientDoctorAssignment.objects.count(),
            'records': MedicalRecord.objects.count(), 'diseases': ChronicDisease.objects.count(),
            'allergies': Allergy.objects.count(), 'treatments': Treatment.objects.count(),
            'consultations': Consultation.objects.count(), 'pressures': BloodPressure.objects.count(),
            'glucoses': BloodGlucose.objects.count(), 'alerts': MedicalAlert.objects.count(),
            'notifications': Notification.objects.count(),
        }
