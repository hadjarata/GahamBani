from django.contrib import admin

from .models import MedicalAlert


@admin.register(MedicalAlert)
class MedicalAlertAdmin(admin.ModelAdmin):
    list_display = ('patient', 'type', 'niveau', 'status', 'source', 'created_at', 'updated_at')
    search_fields = ('patient__user__email', 'message')
    list_filter = ('type', 'niveau', 'status', 'source')
