from django.test import TestCase

from accounts.models import User, UserRole
from profiles.models import PatientProfile

from .models import AlertLevel, AlertSource, AlertStatus, AlertType
from .services import AlertService


class AlertServiceTests(TestCase):
    def test_create_alert_uses_the_status_field(self):
        user = User.objects.create_user(
            email='patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        patient = PatientProfile.objects.create(
            user=user,
            date_naissance='1990-01-01',
            sexe='FEMALE',
            poids='65.00',
            taille='168.00',
        )

        alert = AlertService.create_alert(
            patient=patient,
            alert_type=AlertType.HYPERTENSION,
            niveau=AlertLevel.WARNING,
            message='Tension élevée détectée.',
            source=AlertSource.SYSTEM_RULE,
        )

        self.assertEqual(alert.status, AlertStatus.NEW)
        self.assertEqual(alert.type, AlertType.HYPERTENSION)
