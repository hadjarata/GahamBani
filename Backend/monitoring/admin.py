from django.contrib import admin

from .models import BloodGlucose, BloodPressure


@admin.register(BloodPressure)
class BloodPressureAdmin(admin.ModelAdmin):
    list_display = (
        'patient',
        'systolique',
        'diastolique',
        'frequence_cardiaque',
        'position',
        'bras_utilise',
        'date_mesure',
        'source_mesure',
    )
    search_fields = ('patient__user__email', 'patient__user__first_name', 'patient__user__last_name')
    list_filter = ('source_mesure', 'measurement_context', 'position', 'bras_utilise')


@admin.register(BloodGlucose)
class BloodGlucoseAdmin(admin.ModelAdmin):
    list_display = (
        'patient',
        'valeur',
        'unite',
        'type_mesure',
        'contexte_repas',
        'hba1c',
        'type_prelevement',
        'date_mesure',
        'heure_mesure',
    )
    search_fields = ('patient__user__email', 'patient__user__first_name', 'patient__user__last_name')
    list_filter = ('unite', 'type_mesure', 'contexte_repas', 'type_prelevement', 'source_mesure')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('patient', 'valeur', 'unite', 'type_mesure', 'contexte_repas'),
        }),
        ('Additional information', {
            'fields': ('hba1c', 'heure_mesure', 'type_prelevement', 'source_mesure'),
        }),
        ('Notes', {
            'fields': ('notes',),
        }),
        ('Audit information', {
            'fields': ('date_mesure', 'created_at', 'updated_at'),
        }),
    )
