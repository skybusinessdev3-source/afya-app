# ====================================
# Admin Audit
# ====================================

from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'module', 'object_repr', 'result', 'ip_address')
    list_filter = ('action', 'module', 'result')
    search_fields = ('user__username', 'object_repr', 'object_id')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # le journal ne se modifie pas, ne se supprime pas