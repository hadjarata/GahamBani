from datetime import timedelta
from decimal import Decimal
from importlib import import_module

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from accounts.tokens import VersionedRefreshToken
from profiles.models import DoctorProfile, PatientProfile
from profiles.services import assign_doctor_to_patient, end_doctor_patient_assignment

from .models import (
    BloodGlucose,
    BloodPressure,
    GlucoseUnit,
    MeasurementSource,
)


def create_patient(email='patient@example.com', *, active=True):
    user = User.objects.create_user(
        email=email,
        password='SafePassword2026!',
        role=UserRole.PATIENT,
        is_active=active,
    )
    profile = PatientProfile.objects.create(
        user=user,
        date_naissance='1990-01-01',
        sexe='FEMALE',
        poids='65.00',
        taille='168.00',
    )
    return user, profile


def create_doctor(email='doctor@example.com', registration='MED-001'):
    user = User.objects.create_user(
        email=email,
        password='SafePassword2026!',
        role=UserRole.DOCTOR,
    )
    profile = DoctorProfile.objects.create(
        user=user,
        specialite='Médecine interne',
        numero_ordre=registration,
        hopital='Hôpital central',
        annees_experience=8,
    )
    return user, profile


def create_pressure(patient, *, measured_at=None, systolic=120, diastolic=80):
    return BloodPressure.objects.create(
        patient=patient,
        systolique=systolic,
        diastolique=diastolic,
        frequence_cardiaque=70,
        date_mesure=measured_at or timezone.now(),
    )


def create_glucose(patient, *, measured_at=None, value='1.10', unit=GlucoseUnit.G_PER_L):
    return BloodGlucose.objects.create(
        patient=patient,
        valeur=value,
        unite=unit,
        date_mesure=measured_at or timezone.now(),
    )


def authenticate(client, user):
    token = VersionedRefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')


class MonitoringModelConstraintTests(TestCase):
    def setUp(self):
        self.user, self.patient = create_patient()

    def test_pressure_rejects_systolic_not_above_diastolic(self):
        measurement = BloodPressure(
            patient=self.patient,
            systolique=80,
            diastolique=80,
            date_mesure=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            measurement.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            BloodPressure.objects.create(
                patient=self.patient,
                systolique=80,
                diastolique=80,
                date_mesure=timezone.now(),
            )

    def test_pressure_rejects_technical_bounds_in_python_and_database(self):
        measurement = BloodPressure(
            patient=self.patient,
            systolique=301,
            diastolique=80,
            frequence_cardiaque=251,
            date_mesure=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            measurement.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            BloodPressure.objects.create(
                patient=self.patient,
                systolique=301,
                diastolique=80,
                date_mesure=timezone.now(),
            )

    def test_glucose_rejects_nonpositive_and_unit_inconsistent_values(self):
        measurement = BloodGlucose(
            patient=self.patient,
            valeur=Decimal('0'),
            unite=GlucoseUnit.G_PER_L,
            date_mesure=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            measurement.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            BloodGlucose.objects.create(
                patient=self.patient,
                valeur=Decimal('100'),
                unite=GlucoseUnit.G_PER_L,
                date_mesure=timezone.now(),
            )

    def test_future_date_and_inactive_patient_are_rejected_in_python(self):
        future = BloodPressure(
            patient=self.patient,
            systolique=120,
            diastolique=80,
            date_mesure=timezone.now() + timedelta(minutes=1),
        )
        with self.assertRaises(ValidationError):
            future.full_clean()

        self.user.is_active = False
        self.user.save(update_fields=('is_active',))
        inactive = BloodGlucose(
            patient=self.patient,
            valeur=Decimal('1.10'),
            unite=GlucoseUnit.G_PER_L,
            date_mesure=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            inactive.full_clean()

    def test_pressure_comment_migration_preserves_both_sources(self):
        migration = import_module('monitoring.migrations.0008_monitoring_api_integrity')

        self.assertEqual(migration.merge_comment_and_notes('legacy', ''), 'legacy')
        self.assertEqual(migration.merge_comment_and_notes('legacy', 'current'), 'current\n\nlegacy')
        self.assertEqual(migration.merge_comment_and_notes('same', 'same'), 'same')


class PatientMonitoringAPITests(APITestCase):
    def setUp(self):
        self.user, self.patient = create_patient()
        self.other_user, self.other_patient = create_patient('other-patient@example.com')
        authenticate(self.client, self.user)
        self.pressure_list_url = reverse('blood-pressure-list')
        self.glucose_list_url = reverse('blood-glucose-list')

    def pressure_payload(self, **overrides):
        data = {
            'systolique': 120,
            'diastolique': 80,
            'frequence_cardiaque': 70,
            'date_mesure': timezone.now().isoformat(),
            'notes': 'Mesure à domicile',
        }
        data.update(overrides)
        return data

    def glucose_payload(self, **overrides):
        data = {
            'valeur': '1.10',
            'unite': GlucoseUnit.G_PER_L,
            'date_mesure': timezone.now().isoformat(),
            'notes': 'Avant petit-déjeuner',
        }
        data.update(overrides)
        return data

    def test_patient_creates_own_pressure_and_glucose_with_manual_source(self):
        pressure_response = self.client.post(
            self.pressure_list_url,
            self.pressure_payload(source_mesure=MeasurementSource.DEVICE),
            format='json',
        )
        glucose_response = self.client.post(
            self.glucose_list_url,
            self.glucose_payload(),
            format='json',
        )

        self.assertEqual(pressure_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(glucose_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(pressure_response.data['patient_id'], str(self.patient.pk))
        self.assertEqual(glucose_response.data['patient_id'], str(self.patient.pk))
        self.assertEqual(pressure_response.data['source_mesure'], MeasurementSource.MANUAL)

    def test_patient_cannot_choose_or_replace_owner(self):
        create_response = self.client.post(
            self.pressure_list_url,
            self.pressure_payload(patient_id=str(self.other_patient.pk)),
            format='json',
        )
        measurement = create_pressure(self.patient)
        patch_response = self.client.patch(
            reverse('blood-pressure-detail', args=(measurement.pk,)),
            {'patient_id': str(self.other_patient.pk)},
            format='json',
        )

        self.assertEqual(create_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(patch_response.status_code, status.HTTP_400_BAD_REQUEST)
        measurement.refresh_from_db()
        self.assertEqual(measurement.patient, self.patient)

    def test_patient_without_profile_and_wrong_role_cannot_create(self):
        no_profile = User.objects.create_user(
            email='no-profile@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        authenticate(self.client, no_profile)
        no_profile_response = self.client.post(
            self.pressure_list_url,
            self.pressure_payload(),
            format='json',
        )
        doctor, _ = create_doctor()
        authenticate(self.client, doctor)
        doctor_response = self.client.post(
            self.pressure_list_url,
            self.pressure_payload(),
            format='json',
        )

        self.assertEqual(no_profile_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(doctor_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_measurements_return_400(self):
        pressure_response = self.client.post(
            self.pressure_list_url,
            self.pressure_payload(systolique=70, diastolique=80),
            format='json',
        )
        glucose_response = self.client.post(
            self.glucose_list_url,
            self.glucose_payload(valeur='100'),
            format='json',
        )

        self.assertEqual(pressure_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(glucose_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patient_list_and_detail_never_leak_other_patient(self):
        own = create_pressure(self.patient)
        other = create_pressure(self.other_patient)

        list_response = self.client.get(self.pressure_list_url)
        own_response = self.client.get(reverse('blood-pressure-detail', args=(own.pk,)))
        other_response = self.client.get(reverse('blood-pressure-detail', args=(other.pk,)))

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in list_response.data['results']], [str(own.pk)])
        self.assertEqual(own_response.status_code, status.HTTP_200_OK)
        self.assertEqual(other_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_can_patch_owned_measurement_but_not_delete_it(self):
        own = create_pressure(self.patient)
        other = create_pressure(self.other_patient)

        patch_response = self.client.patch(
            reverse('blood-pressure-detail', args=(own.pk,)),
            {'notes': 'Valeur corrigée', 'source_mesure': MeasurementSource.DEVICE},
            format='json',
        )
        foreign_patch = self.client.patch(
            reverse('blood-pressure-detail', args=(other.pk,)),
            {'notes': 'Intrusion'},
            format='json',
        )
        delete_response = self.client.delete(reverse('blood-pressure-detail', args=(own.pk,)))

        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(foreign_patch.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        own.refresh_from_db()
        self.assertEqual(own.source_mesure, MeasurementSource.MANUAL)

    def test_unauthenticated_admin_and_inactive_users_are_refused(self):
        self.client.credentials()
        self.assertEqual(
            self.client.get(self.pressure_list_url).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        admin_user = User.objects.create_user(
            email='api-admin@example.com',
            password='SafePassword2026!',
            role=UserRole.ADMIN,
        )
        authenticate(self.client, admin_user)
        self.assertEqual(
            self.client.get(self.pressure_list_url).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        authenticate(self.client, self.user)
        self.user.is_active = False
        self.user.save(update_fields=('is_active',))
        self.assertEqual(
            self.client.get(self.pressure_list_url).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class DoctorMonitoringAPITests(APITestCase):
    def setUp(self):
        self.doctor_user, self.doctor = create_doctor()
        self.patient_user, self.patient = create_patient()
        self.other_user, self.other_patient = create_patient('unassigned@example.com')
        self.assignment = assign_doctor_to_patient(
            doctor_user=self.doctor_user,
            patient_user=self.patient_user,
        )
        self.own_patient_measurement = create_pressure(self.patient)
        self.other_measurement = create_pressure(self.other_patient)
        authenticate(self.client, self.doctor_user)
        self.url = reverse('blood-pressure-list')

    def test_assigned_doctor_can_list_and_retrieve_but_not_write(self):
        list_response = self.client.get(self.url)
        detail_response = self.client.get(
            reverse('blood-pressure-detail', args=(self.own_patient_measurement.pk,)),
        )
        create_response = self.client.post(self.url, {}, format='json')
        patch_response = self.client.patch(
            reverse('blood-pressure-detail', args=(self.own_patient_measurement.pk,)),
            {'notes': 'Doctor edit'},
            format='json',
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data['results']), 1)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassigned_and_ended_assignments_grant_no_access(self):
        unassigned_detail = self.client.get(
            reverse('blood-pressure-detail', args=(self.other_measurement.pk,)),
        )
        end_doctor_patient_assignment(self.assignment)
        ended_list = self.client.get(self.url)
        ended_detail = self.client.get(
            reverse('blood-pressure-detail', args=(self.own_patient_measurement.pk,)),
        )

        self.assertEqual(unassigned_detail.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ended_list.data['count'], 0)
        self.assertEqual(ended_detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactive_doctor_or_patient_is_refused(self):
        self.patient_user.is_active = False
        self.patient_user.save(update_fields=('is_active',))
        self.assertEqual(self.client.get(self.url).data['count'], 0)

        self.patient_user.is_active = True
        self.patient_user.save(update_fields=('is_active',))
        authenticate(self.client, self.doctor_user)
        self.doctor_user.is_active = False
        self.doctor_user.save(update_fields=('is_active',))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patient_filter_is_limited_to_current_assignments(self):
        assigned_response = self.client.get(self.url, {'patient_id': self.patient.pk})
        unassigned_response = self.client.get(self.url, {'patient_id': self.other_patient.pk})

        self.assertEqual(assigned_response.data['count'], 1)
        self.assertEqual(unassigned_response.data['count'], 0)

    def test_multiple_assigned_patients_are_returned(self):
        assign_doctor_to_patient(
            doctor_user=self.doctor_user,
            patient_user=self.other_user,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.data['count'], 2)


class MonitoringFilterPaginationTests(APITestCase):
    def setUp(self):
        self.user, self.patient = create_patient('filters@example.com')
        authenticate(self.client, self.user)
        self.url = reverse('blood-pressure-list')
        now = timezone.now()
        self.oldest = create_pressure(self.patient, measured_at=now - timedelta(days=3))
        self.middle = create_pressure(self.patient, measured_at=now - timedelta(days=2))
        self.latest = create_pressure(self.patient, measured_at=now - timedelta(days=1))

    def test_date_filters_and_complete_range(self):
        date_from = self.middle.date_mesure.isoformat()
        date_to = self.latest.date_mesure.isoformat()

        response = self.client.get(self.url, {'date_from': date_from, 'date_to': date_to})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

        from_only = self.client.get(self.url, {'date_from': date_from})
        to_only = self.client.get(self.url, {'date_to': date_to})
        self.assertEqual(from_only.data['count'], 2)
        self.assertEqual(to_only.data['count'], 3)

    def test_invalid_or_reversed_dates_are_rejected(self):
        invalid = self.client.get(self.url, {'date_from': 'not-a-date'})
        reversed_range = self.client.get(
            self.url,
            {'date_from': '2026-07-16', 'date_to': '2026-07-01'},
        )

        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(reversed_range.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ordering_and_pagination(self):
        default_ordering = self.client.get(self.url, {'page_size': 1})
        ascending = self.client.get(self.url, {'ordering': 'date_mesure', 'page_size': 2})
        invalid = self.client.get(self.url, {'ordering': 'patient'})

        self.assertEqual(ascending.status_code, status.HTTP_200_OK)
        self.assertEqual(ascending.data['count'], 3)
        self.assertEqual(len(ascending.data['results']), 2)
        self.assertEqual(ascending.data['results'][0]['id'], str(self.oldest.pk))
        self.assertEqual(default_ordering.data['results'][0]['id'], str(self.latest.pk))
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patient_filter_is_not_available_to_patients(self):
        response = self.client.get(self.url, {'patient_id': self.patient.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MonitoringOpenAPITests(APITestCase):
    def test_schema_documents_monitoring_without_delete_or_put(self):
        response = self.client.get(reverse('schema'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for path in (
            '/api/monitoring/blood-pressure/',
            '/api/monitoring/blood-glucose/',
        ):
            self.assertIn(path, response.data['paths'])
            self.assertIn('get', response.data['paths'][path])
            self.assertIn('post', response.data['paths'][path])
            parameters = {
                parameter['name']
                for parameter in response.data['paths'][path]['get']['parameters']
            }
            self.assertTrue({'date_from', 'date_to', 'ordering', 'patient_id'}.issubset(parameters))

        detail = response.data['paths']['/api/monitoring/blood-pressure/{id}/']
        self.assertIn('get', detail)
        self.assertIn('patch', detail)
        self.assertNotIn('delete', detail)
        self.assertNotIn('put', detail)
