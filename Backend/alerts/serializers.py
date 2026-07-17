from rest_framework import serializers

from .models import MedicalAlert


class MedicalAlertSerializer(serializers.ModelSerializer):
    patient_id = serializers.UUIDField(read_only=True)
    handled_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = MedicalAlert
        fields = (
            'id', 'patient_id', 'type', 'niveau', 'status', 'source',
            'rule_code', 'rule_name', 'message', 'source_type', 'source_id',
            'observed_value', 'unit', 'detected_at', 'acknowledged_at',
            'resolved_at', 'dismissed_at', 'handled_by_id', 'status_reason',
            'metadata', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class AlertTransitionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)
