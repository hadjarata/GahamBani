from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User, UserRole
from profiles.models import PatientProfile

from .models import BloodGlucose, BloodPressure, GlucoseUnit


class MeasurementValidationTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            email='patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=user,
            date_naissance='1990-01-01',
            sexe='FEMALE',
            poids='65.00',
            taille='168.00',
        )

    def test_low_blood_pressure_can_be_recorded(self):
        measurement = BloodPressure(
            patient=self.patient,
            systolique=85,
            diastolique=55,
            date_mesure=timezone.now(),
        )

        measurement.full_clean()

    def test_pressure_rejects_inconsistent_or_future_measurements(self):
        measurement = BloodPressure(
            patient=self.patient,
            systolique=70,
            diastolique=80,
            date_mesure=timezone.now() + timedelta(minutes=5),
        )

        with self.assertRaises(ValidationError) as context:
            measurement.full_clean()

        self.assertIn('systolique', context.exception.message_dict)
        self.assertIn('date_mesure', context.exception.message_dict)

    def test_glucose_limits_follow_the_selected_unit(self):
        measurement = BloodGlucose(
            patient=self.patient,
            valeur=Decimal('100'),
            unite=GlucoseUnit.G_PER_L,
            date_mesure=timezone.now(),
        )

        with self.assertRaises(ValidationError) as context:
            measurement.full_clean()

        self.assertIn('valeur', context.exception.message_dict)
