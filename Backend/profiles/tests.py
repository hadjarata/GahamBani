from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User, UserRole

from .models import (
    AssignmentStatus,
    DoctorProfile,
    PatientDoctorAssignment,
    PatientProfile,
)


class PatientDoctorAssignmentTests(TestCase):
    def setUp(self):
        patient_user = User.objects.create_user(
            email='patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        doctor_user = User.objects.create_user(
            email='doctor@example.com',
            password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )
        self.patient = PatientProfile.objects.create(
            user=patient_user,
            date_naissance='1990-01-01',
            sexe='FEMALE',
            poids='65.00',
            taille='168.00',
        )
        self.doctor = DoctorProfile.objects.create(
            user=doctor_user,
            specialite='Médecine interne',
            numero_ordre='MED-001',
            hopital='Hôpital central',
            annees_experience=8,
        )

    def test_active_assignment_connects_doctor_and_patient(self):
        assignment = PatientDoctorAssignment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
        )

        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)
        self.assertIn(self.patient, self.doctor.patients.all())
        self.assertIn(self.doctor, self.patient.doctors.all())

    def test_ended_assignment_requires_an_end_date(self):
        assignment = PatientDoctorAssignment(
            patient=self.patient,
            doctor=self.doctor,
            status=AssignmentStatus.ENDED,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

        assignment.ended_at = timezone.now()
        assignment.full_clean()


class ProfileRoleTests(TestCase):
    def test_patient_profile_rejects_a_doctor_user(self):
        doctor_user = User.objects.create_user(
            email='doctor-only@example.com',
            password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )
        profile = PatientProfile(
            user=doctor_user,
            date_naissance='1990-01-01',
            sexe='OTHER',
            poids='70.00',
            taille='170.00',
        )

        with self.assertRaises(ValidationError):
            profile.full_clean()
