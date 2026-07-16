from .models import AlertStatus, MedicalAlert


class AlertService:
    """Centralize medical-alert creation."""

    @staticmethod
    def create_alert(
        patient,
        alert_type,
        niveau,
        message,
        source,
        status=AlertStatus.NEW,
    ):
        alert = MedicalAlert(
            patient=patient,
            type=alert_type,
            niveau=niveau,
            message=message,
            source=source,
            status=status,
        )
        alert.full_clean()
        alert.save()
        return alert
