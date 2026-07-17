from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'type', 'priority', 'is_read', 'source_type', 'source_id', 'created_at')
    list_filter = ('type', 'priority', 'is_read', 'created_at')
    search_fields = ('recipient__email', 'recipient_reference', 'source_id', 'event_code')
    list_select_related = ('recipient', 'patient__user')
    date_hierarchy = 'created_at'
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
