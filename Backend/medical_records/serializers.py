from django.urls import reverse
from rest_framework import serializers

from .models import (
    Allergy,
    ChronicDisease,
    Consultation,
    MedicalDocument,
    MedicalNote,
    MedicalRecord,
    Treatment,
)
from .services import patient_user_for_object
from .validators import validate_uploaded_medical_document


class PatientIDField(serializers.UUIDField):
    def get_attribute(self, instance):
        return instance

    def to_representation(self, value):
        return str(patient_user_for_object(value).patient_profile.pk)


class ClinicalSerializer(serializers.ModelSerializer):
    patient_id = PatientIDField(required=False)

    def validate(self, attrs):
        if self.instance is not None and 'patient_id' in attrs:
            raise serializers.ValidationError({'patient_id': 'Le propriétaire est immuable.'})
        return attrs


class MedicalRecordSerializer(serializers.ModelSerializer):
    patient_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = MedicalRecord
        fields = (
            'id', 'patient_id', 'groupe_sanguin', 'antecedents_familiaux',
            'legacy_allergies_text', 'legacy_chronic_diseases_text',
            'legacy_current_treatments_text', 'legacy_medical_notes_text',
            'created_at', 'updated_at',
        )
        read_only_fields = fields


class ChronicDiseaseSerializer(ClinicalSerializer):
    class Meta:
        model = ChronicDisease
        fields = (
            'id', 'patient_id', 'nom_maladie', 'date_diagnostic', 'date_resolution',
            'gravite', 'statut', 'notes', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class AllergySerializer(ClinicalSerializer):
    class Meta:
        model = Allergy
        fields = (
            'id', 'patient_id', 'nom', 'gravite', 'reaction', 'is_active', 'notes',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class TreatmentSerializer(ClinicalSerializer):
    prescriber_id = serializers.UUIDField(source='prescrit_par_id', read_only=True)

    class Meta:
        model = Treatment
        fields = (
            'id', 'patient_id', 'nom_medicament', 'description', 'dosage', 'frequence',
            'voie_administration', 'date_debut', 'date_fin', 'prescriber_id', 'statut',
            'notes', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'prescriber_id', 'created_at', 'updated_at')


class ConsultationSerializer(ClinicalSerializer):
    doctor_id = serializers.UUIDField(source='medecin_id', read_only=True)

    class Meta:
        model = Consultation
        fields = (
            'id', 'patient_id', 'doctor_id', 'date_consultation', 'motif', 'diagnostic',
            'symptomes', 'observations', 'notes', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'doctor_id', 'created_at', 'updated_at')


class MedicalNoteSerializer(ClinicalSerializer):
    author_id = serializers.UUIDField(source='auteur_id', read_only=True)

    class Meta:
        model = MedicalNote
        fields = ('id', 'patient_id', 'author_id', 'contenu', 'created_at', 'updated_at')
        read_only_fields = ('id', 'author_id', 'created_at', 'updated_at')


class MedicalDocumentSerializer(ClinicalSerializer):
    uploader_id = serializers.UUIDField(source='uploaded_by_id', read_only=True)
    download_url = serializers.SerializerMethodField()
    fichier = serializers.FileField(write_only=True, validators=[validate_uploaded_medical_document])

    class Meta:
        model = MedicalDocument
        fields = (
            'id', 'patient_id', 'titre', 'type_document', 'fichier', 'original_filename',
            'mime_type', 'file_size', 'upload_source', 'description', 'date_document',
            'uploader_id', 'download_url', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'original_filename', 'mime_type', 'file_size', 'upload_source',
            'uploader_id', 'download_url', 'created_at', 'updated_at',
        )

    def get_download_url(self, obj) -> str:
        request = self.context.get('request')
        path = reverse('medical-records:document-download', kwargs={'pk': obj.pk})
        return request.build_absolute_uri(path) if request else path
