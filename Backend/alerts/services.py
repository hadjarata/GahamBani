from .models import MedicalAlert


class AlertService:
    """Placeholder for alert creation and retrieval logic."""

    @staticmethod
    def create_alert(patient, type, niveau, message, source, is_read=False):
        return MedicalAlert.objects.create(
            patient=patient,
            type=type,
            niveau=niveau,
            message=message,
            source=source,
            is_read=is_read,
        )
