import json
import shutil
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from accounts.tokens import VersionedRefreshToken
from medical_records.models import ChronicDisease, MedicalRecord
from monitoring.models import BloodPressure
from profiles.models import DoctorProfile, PatientProfile
from profiles.services import assign_doctor_to_patient

from .admin import MedicalAuditEventAdmin
from .context import get_client_ip
from .middleware import RequestIDMiddleware
from .models import AuditAction, AuditDomain, MedicalAuditEvent
from .services import record_medical_audit_event, sanitize_audit_json


def create_patient(email='audit-patient@example.com'):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.PATIENT)
    profile = PatientProfile.objects.create(
        user=user, date_naissance='1990-01-01', sexe='FEMALE', poids='65', taille='168',
    )
    return user, profile


def create_doctor(email='audit-doctor@example.com', registration='AUDIT-MED-1'):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.DOCTOR)
    profile = DoctorProfile.objects.create(
        user=user, specialite='Médecine interne', numero_ordre=registration,
        hopital='Central', annees_experience=8,
    )
    return user, profile


def authenticate(client, user):
    token = VersionedRefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')


class AuditModelAndServiceTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            email='standalone-actor@example.com', password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )
        self.patient_user, self.patient = create_patient()

    def create_event(self, **overrides):
        data = {
            'action': AuditAction.VIEW,
            'domain': AuditDomain.MONITORING,
            'resource_type': 'monitoring.bloodpressure',
            'resource_id': uuid.uuid4(),
            'actor': self.actor,
            'patient': self.patient,
        }
        data.update(overrides)
        return record_medical_audit_event(**data)

    def test_event_captures_historical_actor_and_patient_references(self):
        event = self.create_event()
        self.assertEqual(event.actor_reference, self.actor.pk)
        self.assertEqual(event.actor_role, UserRole.DOCTOR)
        self.assertEqual(event.patient_reference, self.patient.pk)

        self.actor.delete()
        self.patient.delete()
        event.refresh_from_db()
        self.assertIsNone(event.actor)
        self.assertIsNone(event.patient)
        self.assertIsNotNone(event.actor_reference)
        self.assertIsNotNone(event.patient_reference)

    def test_deactivation_does_not_remove_event(self):
        event = self.create_event()
        self.actor.is_active = False
        self.actor.save(update_fields=('is_active',))
        self.assertTrue(MedicalAuditEvent.objects.filter(pk=event.pk).exists())

    def test_instance_queryset_update_and_deletion_are_forbidden(self):
        event = self.create_event()
        event.endpoint = 'changed'
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            MedicalAuditEvent.objects.filter(pk=event.pk).update(endpoint='changed')
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            MedicalAuditEvent.objects.filter(pk=event.pk).delete()

    def test_metadata_removes_secrets_binary_paths_and_limits_values(self):
        cleaned = sanitize_audit_json({
            'password': 'secret',
            'nested': {'Authorization': 'Bearer jwt', 'cookie': 'x', 'safe': 'a' * 900},
            'file_path': 'C:/private/result.pdf',
            'payload': b'%PDF-secret',
            'changed_fields': ['systolique'],
        })
        serialized = json.dumps(cleaned).lower()
        for forbidden in ('password', 'authorization', 'cookie', 'file_path', '%pdf-secret'):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(len(cleaned['nested']['safe']), 512)
        self.assertEqual(cleaned['changed_fields'], ['systolique'])
        oversized = sanitize_audit_json({
            f'field_{index}': 'x' * 512 for index in range(50)
        })
        self.assertEqual(oversized, {'truncated': True})

    def test_audit_failure_is_best_effort(self):
        with self.assertLogs('medical_audit', level='ERROR'):
            with patch.object(MedicalAuditEvent.objects, 'create', side_effect=RuntimeError('database unavailable')):
                self.assertIsNone(self.create_event())


class AuditContextAndAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            'audit-admin@example.com', 'SafePassword2026!',
        )

    def test_request_id_is_validated_and_returned(self):
        supplied = uuid.uuid4()
        middleware = RequestIDMiddleware(lambda request: HttpResponse())
        request = self.factory.get('/', HTTP_X_REQUEST_ID=str(supplied))
        response = middleware(request)
        self.assertEqual(request.request_id, supplied)
        self.assertEqual(response['X-Request-ID'], str(supplied))

        invalid_request = self.factory.get('/', HTTP_X_REQUEST_ID='not-a-uuid')
        middleware(invalid_request)
        self.assertIsInstance(invalid_request.request_id, uuid.UUID)

    @override_settings(AUDIT_TRUSTED_PROXY_COUNT=0)
    def test_ip_does_not_trust_forwarded_header_by_default(self):
        request = self.factory.get(
            '/', REMOTE_ADDR='10.0.0.5', HTTP_X_FORWARDED_FOR='198.51.100.20',
        )
        self.assertEqual(get_client_ip(request), '10.0.0.5')

    def test_admin_is_strictly_read_only_for_superuser(self):
        model_admin = MedicalAuditEventAdmin(MedicalAuditEvent, admin.site)
        request = self.factory.get('/admin/medical_audit/medicalauditevent/')
        request.user = self.superuser
        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertIsNone(model_admin.actions)


class MonitoringAuditIntegrationTests(APITestCase):
    def setUp(self):
        self.patient_user, self.patient = create_patient()
        self.doctor_user, _ = create_doctor()
        assign_doctor_to_patient(doctor_user=self.doctor_user, patient_user=self.patient_user)
        authenticate(self.client, self.patient_user)

    def pressure_payload(self, **overrides):
        data = {
            'systolique': 120, 'diastolique': 80, 'frequence_cardiaque': 70,
            'date_mesure': timezone.now().isoformat(),
        }
        data.update(overrides)
        return data

    def test_pressure_and_glucose_creations_are_audited(self):
        pressure = self.client.post(reverse('blood-pressure-list'), self.pressure_payload(), format='json')
        glucose = self.client.post(reverse('blood-glucose-list'), {
            'valeur': '1.10', 'unite': 'G_PER_L', 'date_mesure': timezone.now().isoformat(),
        }, format='json')
        self.assertEqual(pressure.status_code, status.HTTP_201_CREATED)
        self.assertEqual(glucose.status_code, status.HTTP_201_CREATED)
        events = MedicalAuditEvent.objects.filter(action=AuditAction.CREATE)
        self.assertEqual(events.count(), 2)
        self.assertEqual(set(events.values_list('patient_id', flat=True)), {self.patient.pk})
        self.assertEqual(set(events.values_list('actor_id', flat=True)), {self.patient_user.pk})

    def test_patch_records_numeric_before_after_and_real_saved_state(self):
        measurement = BloodPressure.objects.create(
            patient=self.patient, systolique=120, diastolique=80,
            frequence_cardiaque=70, date_mesure=timezone.now(),
        )
        response = self.client.patch(
            reverse('blood-pressure-detail', args=[measurement.pk]),
            {'systolique': 125, 'notes': 'texte médical non copié'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = MedicalAuditEvent.objects.get(action=AuditAction.UPDATE)
        self.assertEqual(event.changes['systolique'], {'before': 120, 'after': 125})
        self.assertNotIn('texte médical', json.dumps(event.metadata, ensure_ascii=False))
        measurement.refresh_from_db()
        self.assertEqual(event.changes['systolique']['after'], measurement.systolique)

    def test_detail_and_list_generate_one_event_each_with_correct_doctor(self):
        measurement = BloodPressure.objects.create(
            patient=self.patient, systolique=120, diastolique=80,
            frequence_cardiaque=70, date_mesure=timezone.now(),
        )
        authenticate(self.client, self.doctor_user)
        list_response = self.client.get(reverse('blood-pressure-list'))
        detail_response = self.client.get(
            reverse('blood-pressure-detail', args=[measurement.pk]),
            REMOTE_ADDR='10.20.30.40', HTTP_USER_AGENT='GahamBani-Mobile/1.0',
            HTTP_X_REQUEST_ID=str(uuid.uuid4()),
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(MedicalAuditEvent.objects.filter(action=AuditAction.LIST).count(), 1)
        detail_event = MedicalAuditEvent.objects.get(action=AuditAction.VIEW)
        self.assertEqual(detail_event.actor_id, self.doctor_user.pk)
        self.assertEqual(detail_event.patient_id, self.patient.pk)
        self.assertEqual(detail_event.ip_address, '10.20.30.40')
        self.assertEqual(detail_event.user_agent, 'GahamBani-Mobile/1.0')
        self.assertEqual(str(detail_event.request_id), detail_response['X-Request-ID'])

    def test_invalid_or_forbidden_operation_never_creates_false_success(self):
        invalid = self.client.post(
            reverse('blood-pressure-list'), self.pressure_payload(systolique=70, diastolique=80),
            format='json',
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(MedicalAuditEvent.objects.exists())

        measurement = BloodPressure.objects.create(
            patient=self.patient, systolique=120, diastolique=80,
            frequence_cardiaque=70, date_mesure=timezone.now(),
        )
        invalid_patch = self.client.patch(
            reverse('blood-pressure-detail', args=[measurement.pk]),
            {'systolique': 70}, format='json',
        )
        self.assertEqual(invalid_patch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(MedicalAuditEvent.objects.exists())

        other_doctor, _ = create_doctor('unassigned-audit@example.com', 'AUDIT-MED-2')
        authenticate(self.client, other_doctor)
        denied = self.client.get(reverse('blood-pressure-detail', args=[measurement.pk]))
        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(MedicalAuditEvent.objects.exists())

    def test_audit_storage_failure_does_not_rollback_valid_measurement(self):
        with self.assertLogs('medical_audit', level='ERROR'):
            with patch.object(MedicalAuditEvent.objects, 'create', side_effect=RuntimeError('audit unavailable')):
                response = self.client.post(
                    reverse('blood-pressure-list'), self.pressure_payload(), format='json',
                )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(BloodPressure.objects.count(), 1)


class MedicalRecordsAuditIntegrationTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='gahambani-audit-')
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.patient_user, self.patient = create_patient('audit-record-patient@example.com')
        self.doctor_user, _ = create_doctor('audit-record-doctor@example.com', 'AUDIT-MED-3')
        assign_doctor_to_patient(doctor_user=self.doctor_user, patient_user=self.patient_user)
        self.record = MedicalRecord.objects.create(patient=self.patient)
        authenticate(self.client, self.doctor_user)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_record_read_and_clinical_creations_are_audited(self):
        record = self.client.get(reverse('medical-records:record'), {'patient_id': self.patient.pk})
        treatment = self.client.post(reverse('medical-records:treatment-list'), {
            'patient_id': str(self.patient.pk), 'nom_medicament': 'Metformine',
            'dosage': '500 mg', 'frequence': '2/j', 'date_debut': '2026-01-01',
        }, format='json')
        consultation = self.client.post(reverse('medical-records:consultation-list'), {
            'patient_id': str(self.patient.pk),
            'date_consultation': (timezone.now() - timedelta(hours=1)).isoformat(),
            'motif': 'Suivi clinique sensible',
        }, format='json')
        note_text = 'Observation médicale très sensible ' * 30
        note = self.client.post(reverse('medical-records:note-list'), {
            'patient_id': str(self.patient.pk), 'contenu': note_text,
        }, format='json')
        for response in (record, treatment, consultation, note):
            self.assertLess(response.status_code, 300, getattr(response, 'data', None))
        self.assertEqual(MedicalAuditEvent.objects.filter(action=AuditAction.CREATE).count(), 3)
        self.assertEqual(MedicalAuditEvent.objects.filter(action=AuditAction.VIEW).count(), 1)
        serialized = json.dumps(list(MedicalAuditEvent.objects.values('metadata', 'changes')), ensure_ascii=False)
        self.assertNotIn(note_text, serialized)
        self.assertIn('text_length', serialized)

    def test_clinical_update_has_only_allowed_short_before_after(self):
        disease = ChronicDisease.objects.create(
            medical_record=self.record, nom_maladie='Pathologie sensible', statut='ACTIVE',
        )
        response = self.client.patch(
            reverse('medical-records:chronic-disease-detail', args=[disease.pk]),
            {'statut': 'CONTROLLED', 'notes': 'un long commentaire non journalisé'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = MedicalAuditEvent.objects.get(action=AuditAction.UPDATE)
        self.assertEqual(event.changes['statut'], {'before': 'ACTIVE', 'after': 'CONTROLLED'})
        self.assertNotIn('long commentaire', json.dumps(event.metadata, ensure_ascii=False))

    def test_note_update_records_length_but_never_text(self):
        original = 'Texte médical initial strictement confidentiel'
        created = self.client.post(reverse('medical-records:note-list'), {
            'patient_id': str(self.patient.pk), 'contenu': original,
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        replacement = 'Nouveau texte médical encore plus sensible'
        response = self.client.patch(
            reverse('medical-records:note-detail', args=[created.data['id']]),
            {'contenu': replacement}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = MedicalAuditEvent.objects.get(action=AuditAction.UPDATE)
        serialized = json.dumps({'metadata': event.metadata, 'changes': event.changes}, ensure_ascii=False)
        self.assertEqual(event.metadata['text_length'], len(replacement))
        self.assertNotIn(original, serialized)
        self.assertNotIn(replacement, serialized)

    def test_upload_and_download_audit_only_safe_file_metadata(self):
        upload = self.client.post(reverse('medical-records:document-list'), {
            'patient_id': str(self.patient.pk), 'titre': 'Analyse', 'type_document': 'ANALYSE',
            'date_document': '2026-01-01',
            'fichier': SimpleUploadedFile('resultat.pdf', b'%PDF-1.4\nsecret-binary\n%%EOF', content_type='application/pdf'),
        }, format='multipart')
        self.assertEqual(upload.status_code, status.HTTP_201_CREATED, upload.data)
        download = self.client.get(
            reverse('medical-records:document-download', args=[upload.data['id']]),
        )
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        create_event = MedicalAuditEvent.objects.get(action=AuditAction.CREATE)
        download_event = MedicalAuditEvent.objects.get(action=AuditAction.DOWNLOAD)
        self.assertEqual(create_event.patient_id, self.patient.pk)
        self.assertEqual(download_event.actor_id, self.doctor_user.pk)
        serialized = json.dumps(
            {'create': create_event.metadata, 'download': download_event.metadata},
        ).lower()
        self.assertIn('resultat.pdf', serialized)
        self.assertNotIn('secret-binary', serialized)
        self.assertNotIn('medical_documents/', serialized)
        self.assertNotIn(str(self.media_root).lower(), serialized)

    def test_invalid_clinical_creation_has_no_success_event(self):
        response = self.client.post(reverse('medical-records:treatment-list'), {
            'patient_id': str(self.patient.pk), 'nom_medicament': 'A',
            'dosage': '1', 'frequence': '1/j', 'date_debut': '2026-02-02',
            'date_fin': '2026-02-01', 'statut': 'STOPPED',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(MedicalAuditEvent.objects.exists())
