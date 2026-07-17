from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from accounts.models import User

from .models import AssignmentStatus, DoctorProfile, PatientDoctorAssignment, PatientProfile, SexChoices


def display_name(user, fallback):
    name = f'{user.first_name} {user.last_name}'.strip()
    return name or fallback


class ProfileUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email', 'phone', 'role')
        read_only_fields = fields


class PatientProfileReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientProfile
        fields = ('id', 'date_naissance', 'sexe', 'poids', 'taille', 'created_at', 'updated_at')
        read_only_fields = fields


class DoctorProfileReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorProfile
        fields = ('id', 'specialite', 'numero_ordre', 'hopital', 'annees_experience', 'created_at', 'updated_at')
        read_only_fields = fields


class StrictProfileWriteSerializer(serializers.ModelSerializer):
    editable_fields = set()

    def validate(self, attrs):
        forbidden = set(self.initial_data) - self.editable_fields
        if forbidden:
            raise serializers.ValidationError({field: 'Ce champ ne peut pas être modifié.' for field in forbidden})
        return attrs

    def validate_text(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError('Ce champ ne peut pas être vide.')
        return normalized


class PatientProfileWriteSerializer(StrictProfileWriteSerializer):
    editable_fields = {'date_naissance', 'sexe', 'poids', 'taille'}
    date_naissance = serializers.DateField(required=False)
    sexe = serializers.ChoiceField(choices=SexChoices.values, required=False)
    poids = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal('0.01'), required=False)
    taille = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal('0.01'), required=False)

    class Meta:
        model = PatientProfile
        fields = ('date_naissance', 'sexe', 'poids', 'taille')

    def validate_date_naissance(self, value):
        if value >= timezone.localdate():
            raise serializers.ValidationError('La date de naissance doit être antérieure à aujourd’hui.')
        return value


class DoctorProfileWriteSerializer(StrictProfileWriteSerializer):
    editable_fields = {'specialite', 'hopital', 'annees_experience'}
    specialite = serializers.CharField(max_length=255, required=False)
    hopital = serializers.CharField(max_length=255, required=False)
    annees_experience = serializers.IntegerField(min_value=0, max_value=100, required=False)

    class Meta:
        model = DoctorProfile
        fields = ('specialite', 'hopital', 'annees_experience')

    def validate_specialite(self, value):
        return self.validate_text(value)

    def validate_hopital(self, value):
        return self.validate_text(value)


class OnboardingSerializer(serializers.Serializer):
    is_complete = serializers.BooleanField()
    completion_percentage = serializers.IntegerField(min_value=0, max_value=100)
    missing_fields = serializers.ListField(child=serializers.CharField())


class PatientMeResponseSerializer(serializers.Serializer):
    user = ProfileUserSerializer()
    profile_type = serializers.CharField()
    profile = PatientProfileReadSerializer()
    onboarding = OnboardingSerializer()


class DoctorMeResponseSerializer(serializers.Serializer):
    user = ProfileUserSerializer()
    profile_type = serializers.CharField()
    profile = DoctorProfileReadSerializer()
    onboarding = OnboardingSerializer()


class MyPatientAssignmentSerializer(serializers.ModelSerializer):
    patient_profile_id = serializers.UUIDField(source='patient_id', read_only=True)
    patient_user_id = serializers.UUIDField(source='patient.user_id', read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = PatientDoctorAssignment
        fields = ('id', 'patient_profile_id', 'patient_user_id', 'display_name', 'assigned_at', 'status')
        read_only_fields = fields

    def get_display_name(self, obj) -> str:
        return display_name(obj.patient.user, 'Patient')


class MyDoctorAssignmentSerializer(serializers.ModelSerializer):
    doctor_profile_id = serializers.UUIDField(source='doctor_id', read_only=True)
    doctor_user_id = serializers.UUIDField(source='doctor.user_id', read_only=True)
    display_name = serializers.SerializerMethodField()
    speciality = serializers.CharField(source='doctor.specialite', read_only=True)
    hospital = serializers.CharField(source='doctor.hopital', read_only=True)

    class Meta:
        model = PatientDoctorAssignment
        fields = ('id', 'doctor_profile_id', 'doctor_user_id', 'display_name', 'speciality', 'hospital', 'assigned_at', 'status')
        read_only_fields = fields

    def get_display_name(self, obj) -> str:
        return display_name(obj.doctor.user, 'Médecin')


class AssignmentHistorySerializer(serializers.ModelSerializer):
    counterpart = serializers.SerializerMethodField()

    class Meta:
        model = PatientDoctorAssignment
        fields = ('id', 'status', 'assigned_at', 'ended_at', 'counterpart')
        read_only_fields = fields

    @extend_schema_field(serializers.DictField())
    def get_counterpart(self, obj) -> dict:
        actor = self.context['request'].user
        if actor.role == 'PATIENT':
            return {
                'profile_id': str(obj.doctor_id),
                'display_name': display_name(obj.doctor.user, 'Médecin'),
                'speciality': obj.doctor.specialite,
                'hospital': obj.doctor.hopital,
            }
        return {
            'profile_id': str(obj.patient_id),
            'user_id': str(obj.patient.user_id),
            'display_name': display_name(obj.patient.user, 'Patient'),
        }


class AssignmentFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=AssignmentStatus.values, required=False)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)
    ordering = serializers.ChoiceField(choices=('assigned_at', '-assigned_at'), default='-assigned_at')
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)

    def validate(self, attrs):
        if attrs.get('date_from') and attrs.get('date_to') and attrs['date_from'] > attrs['date_to']:
            raise serializers.ValidationError({'date_to': 'La date finale doit suivre la date initiale.'})
        return attrs


class PaginatedPatientsSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = MyPatientAssignmentSerializer(many=True)


class PaginatedDoctorsSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = MyDoctorAssignmentSerializer(many=True)


class PaginatedAssignmentsSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = AssignmentHistorySerializer(many=True)
