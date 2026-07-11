from django.contrib import admin

from .models import Allergy, ChronicDisease, MedicalNote, MedicalRecord


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
