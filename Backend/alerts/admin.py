from django.contrib import admin

from .models import MedicalAlert


@admin.register(MedicalAlert)
class MedicalAlertAdmin(admin.ModelAdmin):
    list_display = (
        'patient', 'rule_code', 'type', 'niveau', 'status', 'source',
        'detected_at', 'handled_by',
    )
    search_fields = (
        'patient__user__email', 'rule_code', 'source_type', 'source_id',
        'observed_value',
    )
    list_filter = ('status', 'niveau', 'rule_code', 'type', 'source', 'detected_at')
    list_select_related = ('patient__user', 'handled_by')
    date_hierarchy = 'detected_at'
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
