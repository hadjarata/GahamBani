from django.contrib import admin

from .models import DoctorProfile, PatientProfile


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'date_naissance', 'sexe', 'poids', 'taille', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    list_filter = ('sexe',)


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'specialite', 'numero_ordre', 'hopital', 'annees_experience', 'created_at')
    search_fields = ('user__email', 'specialite', 'hopital', 'numero_ordre')
    list_filter = ('specialite', 'hopital')
