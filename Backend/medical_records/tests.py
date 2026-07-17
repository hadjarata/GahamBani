import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from accounts.tokens import VersionedRefreshToken
from profiles.models import DoctorProfile, PatientProfile
from profiles.services import assign_doctor_to_patient, end_doctor_patient_assignment

from .models import Allergy, ChronicDisease, MedicalNote, MedicalRecord, Treatment


def patient(email='patient-medical@example.com', active=True):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.PATIENT, is_active=active)
    profile = PatientProfile.objects.create(user=user, date_naissance='1990-01-01', sexe='FEMALE', poids='65', taille='168')
    return user, profile


def doctor(email='doctor-medical@example.com', registration='MED-REC-1'):
    user = User.objects.create_user(email=email, password='SafePassword2026!', role=UserRole.DOCTOR)
    profile = DoctorProfile.objects.create(user=user, specialite='Médecine interne', numero_ordre=registration, hopital='Central', annees_experience=8)
    return user, profile


def auth(client, user):
    token = VersionedRefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')


class MedicalRecordConstraintTests(TestCase):
    def setUp(self):
        self.user, self.patient = patient()
        self.doctor, _ = doctor()
        self.record = MedicalRecord.objects.create(patient=self.patient)

    def test_one_record_per_patient_is_database_enforced(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MedicalRecord.objects.create(patient=self.patient)

    def test_active_names_are_case_insensitively_unique(self):
        ChronicDisease.objects.create(medical_record=self.record, nom_maladie='Diabete')
        Allergy.objects.create(medical_record=self.record, nom='Penicilline')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChronicDisease.objects.create(medical_record=self.record, nom_maladie='DIABETE')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Allergy.objects.create(medical_record=self.record, nom='PENICILLINE')

    def test_treatment_dates_and_note_author_are_validated(self):
        invalid = Treatment(
            medical_record=self.record, nom_medicament='A', dosage='1', frequence='1/j',
            date_debut='2026-02-02', date_fin='2026-02-01', prescrit_par=self.doctor,
            statut='STOPPED',
        )
        with self.assertRaises(Exception):
            invalid.full_clean()
        note = MedicalNote(medical_record=self.record, auteur=self.user, contenu='note')
        with self.assertRaises(Exception):
            note.full_clean()


class MedicalRecordAPITests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix='gahambani-medical-')
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.patient_user, self.patient = patient()
        self.other_user, self.other = patient('other-medical@example.com')
        self.doctor_user, self.doctor = doctor()
        self.other_doctor_user, _ = doctor('other-doctor-medical@example.com', 'MED-REC-2')
        self.assignment = assign_doctor_to_patient(doctor_user=self.doctor_user, patient_user=self.patient_user)
        self.record = MedicalRecord.objects.create(patient=self.patient, groupe_sanguin='O_POSITIVE')
        self.other_record = MedicalRecord.objects.create(patient=self.other)
        self.disease = ChronicDisease.objects.create(medical_record=self.record, nom_maladie='Diabète')
        self.note = MedicalNote.objects.create(medical_record=self.record, auteur=self.doctor_user, contenu='Visible au patient')

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_patient_reads_only_own_record_and_all_notes(self):
        auth(self.client, self.patient_user)
        response = self.client.get(reverse('medical-records:record'))
        notes = self.client.get(reverse('medical-records:note-list'))
        forbidden_filter = self.client.get(reverse('medical-records:note-list'), {'patient_id': self.other.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['patient_id'], str(self.patient.pk))
        self.assertEqual(notes.data['results'][0]['contenu'], 'Visible au patient')
        self.assertEqual(forbidden_filter.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patient_cannot_create_or_modify_clinical_data(self):
        auth(self.client, self.patient_user)
        create = self.client.post(reverse('medical-records:allergy-list'), {'nom': 'Latex'}, format='json')
        patch = self.client.patch(reverse('medical-records:chronic-disease-detail', args=[self.disease.pk]), {'notes': 'altéré'}, format='json')
        self.assertEqual(create.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(patch.status_code, status.HTTP_403_FORBIDDEN)

    def test_assigned_doctor_can_create_all_clinical_resources(self):
        auth(self.client, self.doctor_user)
        cases = [
            ('medical-records:chronic-disease-list', {'patient_id': str(self.patient.pk), 'nom_maladie': 'Hypertension'}),
            ('medical-records:allergy-list', {'patient_id': str(self.patient.pk), 'nom': 'Latex'}),
            ('medical-records:treatment-list', {'patient_id': str(self.patient.pk), 'nom_medicament': 'Metformine', 'dosage': '500 mg', 'frequence': '2/j', 'date_debut': '2026-01-01'}),
            ('medical-records:consultation-list', {'patient_id': str(self.patient.pk), 'date_consultation': (timezone.now() - timedelta(hours=1)).isoformat(), 'motif': 'Suivi'}),
            ('medical-records:note-list', {'patient_id': str(self.patient.pk), 'contenu': 'Nouvelle note'}),
        ]
        for url_name, payload in cases:
            with self.subTest(url=url_name):
                response = self.client.post(reverse(url_name), payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertEqual(response.data['patient_id'], str(self.patient.pk))

    def test_unassigned_and_former_doctors_have_no_access(self):
        auth(self.client, self.other_doctor_user)
        self.assertEqual(self.client.get(reverse('medical-records:chronic-disease-detail', args=[self.disease.pk])).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(reverse('medical-records:note-list'), {'patient_id': str(self.patient.pk), 'contenu': 'x'}, format='json').status_code, status.HTTP_403_FORBIDDEN)
        end_doctor_patient_assignment(self.assignment)
        auth(self.client, self.doctor_user)
        self.assertEqual(self.client.get(reverse('medical-records:chronic-disease-detail', args=[self.disease.pk])).status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_cannot_change_owner_or_another_authors_note(self):
        auth(self.client, self.doctor_user)
        owner = self.client.patch(reverse('medical-records:chronic-disease-detail', args=[self.disease.pk]), {'patient_id': str(self.other.pk)}, format='json')
        self.assertEqual(owner.status_code, status.HTTP_400_BAD_REQUEST)
        assign_doctor_to_patient(doctor_user=self.other_doctor_user, patient_user=self.patient_user)
        auth(self.client, self.other_doctor_user)
        note = self.client.patch(reverse('medical-records:note-detail', args=[self.note.pk]), {'contenu': 'réécrit'}, format='json')
        self.assertEqual(note.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_is_denied_and_put_delete_are_disabled(self):
        admin = User.objects.create_superuser('admin-medical@example.com', 'SafePassword2026!')
        auth(self.client, admin)
        self.assertEqual(self.client.get(reverse('medical-records:allergy-list')).status_code, status.HTTP_403_FORBIDDEN)
        auth(self.client, self.doctor_user)
        detail = reverse('medical-records:chronic-disease-detail', args=[self.disease.pk])
        self.assertEqual(self.client.put(detail, {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(detail).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def upload(self, content=b'%PDF-1.4\n%%EOF', name='analyse.pdf', content_type='application/pdf', **extra):
        payload = {
            'titre': 'Analyse', 'type_document': 'ANALYSE', 'date_document': '2026-01-01',
            'fichier': SimpleUploadedFile(name, content, content_type=content_type), **extra,
        }
        return self.client.post(reverse('medical-records:document-list'), payload, format='multipart')

    def test_patient_uploads_own_valid_document_without_storage_path_leak(self):
        auth(self.client, self.patient_user)
        response = self.upload(name='../dossier.pdf', patient_id=str(self.other.pk))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.upload(name='dossier.pdf')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertNotIn('fichier', response.data)
        self.assertNotIn('medical_documents/', str(response.data))
        self.assertEqual(response.data['upload_source'], 'PATIENT')

    def test_document_rejects_extension_mime_signature_and_size(self):
        auth(self.client, self.patient_user)
        self.assertEqual(self.upload(name='virus.exe').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.upload(content_type='image/png').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.upload(content=b'not-a-pdf').status_code, status.HTTP_400_BAD_REQUEST)
        with override_settings(MEDICAL_DOCUMENT_MAX_SIZE=5):
            self.assertEqual(self.upload(content=b'%PDF-more-than-five').status_code, status.HTTP_400_BAD_REQUEST)

    def test_pdf_jpeg_and_png_are_accepted(self):
        auth(self.client, self.patient_user)
        uploads = (
            ('rapport.pdf', 'application/pdf', b'%PDF-1.4\n%%EOF'),
            ('radio.jpg', 'image/jpeg', b'\xff\xd8\xff\xe0image'),
            ('scan.png', 'image/png', b'\x89PNG\r\n\x1a\nimage'),
        )
        for name, mime, content in uploads:
            with self.subTest(name=name):
                response = self.upload(name=name, content_type=mime, content=content)
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_secure_download_requires_owner_or_current_doctor(self):
        auth(self.client, self.patient_user)
        created = self.upload()
        url = reverse('medical-records:document-download', args=[created.data['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.client.credentials()
        self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)
        auth(self.client, self.other_doctor_user)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        auth(self.client, self.doctor_user)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)

    def test_filters_pagination_and_ordering_are_bounded(self):
        auth(self.client, self.doctor_user)
        url = reverse('medical-records:chronic-disease-list')
        ok = self.client.get(url, {'patient_id': self.patient.pk, 'status': 'ACTIVE', 'page_size': 1})
        bad = self.client.get(url, {'ordering': 'nom_maladie'})
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(len(ok.data['results']), 1)
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_openapi_describes_multipart_upload_and_binary_download(self):
        response = self.client.get(
            reverse('schema'), HTTP_ACCEPT='application/vnd.oai.openapi+json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        paths = response.data['paths']
        upload = paths['/api/medical-records/documents/']['post']
        download = paths['/api/medical-records/documents/{id}/download/']['get']
        self.assertIn('multipart/form-data', upload['requestBody']['content'])
        binary_schema = download['responses']['200']['content']['application/octet-stream']['schema']
        self.assertEqual(binary_schema, {'type': 'string', 'format': 'binary'})
