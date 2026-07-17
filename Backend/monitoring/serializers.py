from copy import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import BloodGlucose, BloodPressure


class MeasurementSerializer(serializers.ModelSerializer):
    patient_id = serializers.UUIDField(source='patient.id', read_only=True)

    def validate(self, attrs):
        forbidden_owner_fields = {'patient', 'patient_id'}.intersection(self.initial_data)
        if forbidden_owner_fields:
            raise serializers.ValidationError({
                field: 'The patient owner is determined from the authenticated account.'
                for field in forbidden_owner_fields
            })

        candidate = copy(self.instance) if self.instance is not None else self.Meta.model()
        if self.instance is None:
            candidate.patient = self.context.get('patient_profile')
        for field, value in attrs.items():
            setattr(candidate, field, value)
        try:
            candidate.full_clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs


class BloodPressureSerializer(MeasurementSerializer):
    class Meta:
        model = BloodPressure
        fields = (
            'id',
            'patient_id',
            'systolique',
            'diastolique',
            'frequence_cardiaque',
            'source_mesure',
            'measurement_context',
            'position',
            'bras_utilise',
            'numero_mesure',
            'notes',
            'date_mesure',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'patient_id',
            'source_mesure',
            'created_at',
            'updated_at',
        )


class BloodGlucoseSerializer(MeasurementSerializer):
    class Meta:
        model = BloodGlucose
        fields = (
            'id',
            'patient_id',
            'valeur',
            'unite',
            'type_mesure',
            'source_mesure',
            'hba1c',
            'contexte_repas',
            'heure_mesure',
            'type_prelevement',
            'notes',
            'date_mesure',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'patient_id',
            'source_mesure',
            'created_at',
            'updated_at',
        )
        extra_kwargs = {
            'unite': {'required': True},
        }
