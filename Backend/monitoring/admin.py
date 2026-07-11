from django.contrib import admin

from .models import BloodGlucose, BloodPressure


@admin.register(BloodPressure)
class BloodPressureAdmin(admin.ModelAdmin):
    list_display = ('patient', 'systolique', 'diastolique', 'date_mesure', 'source_mesure')
    search_fields = ('patient__user__email', 'patient__user__first_name', 'patient__user__last_name')
    list_filter = ('source_mesure', 'measurement_context')


@admin.register(BloodGlucose)
class BloodGlucoseAdmin(admin.ModelAdmin):
    list_display = ('patient', 'valeur', 'unite', 'type_mesure', 'date_mesure')
    search_fields = ('patient__user__email', 'patient__user__first_name', 'patient__user__last_name')
    list_filter = ('unite', 'type_mesure', 'source_mesure')
