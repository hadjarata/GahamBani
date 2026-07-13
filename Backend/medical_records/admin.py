from django.contrib import admin

from .models import Allergy, ChronicDisease, Consultation, MedicalDocument, MedicalNote, MedicalRecord, Treatment


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('patient', 'groupe_sanguin', 'created_at', 'updated_at')
    search_fields = ('patient__user__email', 'patient__user__first_name', 'patient__user__last_name')
    list_filter = ('groupe_sanguin',)


@admin.register(ChronicDisease)
class ChronicDiseaseAdmin(admin.ModelAdmin):
    list_display = ('nom_maladie', 'medical_record', 'gravite', 'statut', 'created_at')
    search_fields = ('nom_maladie', 'medical_record__patient__user__email')
    list_filter = ('gravite', 'statut')


@admin.register(Allergy)
class AllergyAdmin(admin.ModelAdmin):
    list_display = ('nom', 'medical_record', 'gravite', 'reaction', 'created_at')
    search_fields = ('nom', 'medical_record__patient__user__email')
    list_filter = ('gravite',)


@admin.register(MedicalNote)
class MedicalNoteAdmin(admin.ModelAdmin):
    list_display = ('auteur', 'medical_record', 'created_at')
    search_fields = ('auteur__email', 'medical_record__patient__user__email', 'contenu')
    list_filter = ('created_at',)


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
