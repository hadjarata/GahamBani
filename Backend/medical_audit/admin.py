from django.contrib import admin

from .models import MedicalAuditEvent


@admin.register(MedicalAuditEvent)
class MedicalAuditEventAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'action', 'domain', 'resource_type', 'resource_id',
        'actor', 'actor_role', 'patient', 'result', 'request_id',
    )
    list_filter = ('action', 'domain', 'result', 'actor_role', 'created_at')
    search_fields = (
        'resource_id', 'actor__email', 'actor_reference', 'patient_reference',
        'request_id',
    )
    list_select_related = ('actor', 'patient__user')
    date_hierarchy = 'created_at'
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_staff and request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
