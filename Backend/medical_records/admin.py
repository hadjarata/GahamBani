from django.contrib import admin

from .models import Allergy, ChronicDisease, Consultation, MedicalDocument, MedicalNote, MedicalRecord, Treatment


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('patient', 'groupe_sanguin', 'created_at', 'updated_at')
    search_fields = ('patient__user__email', 'patient__user__first_name', 'patient__user__last_name')
    list_filter = ('groupe_sanguin',)
    list_select_related = ('patient__user',)
    autocomplete_fields = ('patient',)
    readonly_fields = (
        'legacy_allergies_text', 'legacy_chronic_diseases_text',
        'legacy_current_treatments_text', 'legacy_medical_notes_text',
        'created_at', 'updated_at',
    )


@admin.register(ChronicDisease)
class ChronicDiseaseAdmin(admin.ModelAdmin):
    list_display = ('nom_maladie', 'medical_record', 'gravite', 'statut', 'created_at')
    search_fields = ('nom_maladie', 'medical_record__patient__user__email')
    list_filter = ('gravite', 'statut')
    list_select_related = ('medical_record__patient__user',)
    autocomplete_fields = ('medical_record',)


@admin.register(Allergy)
class AllergyAdmin(admin.ModelAdmin):
    list_display = ('nom', 'medical_record', 'gravite', 'reaction', 'created_at')
    search_fields = ('nom', 'medical_record__patient__user__email')
    list_filter = ('gravite', 'is_active')
    list_select_related = ('medical_record__patient__user',)
    autocomplete_fields = ('medical_record',)


@admin.register(MedicalNote)
class MedicalNoteAdmin(admin.ModelAdmin):
    list_display = ('auteur', 'medical_record', 'created_at')
    search_fields = ('auteur__email', 'medical_record__patient__user__email', 'contenu')
    list_filter = ('created_at',)
    list_select_related = ('auteur', 'medical_record__patient__user')
    autocomplete_fields = ('auteur', 'medical_record')


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = (
        'nom_medicament',
        'medical_record',
        'statut',
        'date_debut',
        'date_fin',
        'prescrit_par',
        'created_at',
        'updated_at',
    )
    search_fields = (
        'nom_medicament',
        'medical_record__patient__user__email',
        'prescrit_par__email',
    )
    list_filter = ('statut', 'date_debut', 'date_fin')
    list_select_related = ('medical_record__patient__user', 'prescrit_par')
    autocomplete_fields = ('medical_record', 'prescrit_par')


@admin.register(MedicalDocument)
class MedicalDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'titre',
        'type_document',
        'medical_record',
        'date_document',
        'uploaded_by',
        'created_at',
        'updated_at',
    )
    search_fields = (
        'titre',
        'medical_record__patient__user__email',
        'uploaded_by__email',
        'description',
    )
    list_filter = ('type_document', 'date_document')
    list_select_related = ('medical_record__patient__user', 'uploaded_by')
    autocomplete_fields = ('medical_record', 'uploaded_by')
    readonly_fields = ('original_filename', 'mime_type', 'file_size', 'upload_source', 'created_at', 'updated_at')


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = (
        'patient',
        'medecin',
        'date_consultation',
        'created_at',
        'updated_at',
    )
    search_fields = (
        'patient__user__email',
        'medecin__user__email',
        'motif',
        'diagnostic',
    )
    list_filter = ('medecin', 'date_consultation')
    list_select_related = ('patient__user', 'medecin__user')
    autocomplete_fields = ('patient', 'medecin')
