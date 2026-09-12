from django.contrib import admin

from .models import Service, Session


admin.site.register(Service)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('patient', 'motif', 'professional', 'date', 'status')
    list_filter = ('motif', 'status', 'date')
    search_fields = ('patient__last_name', 'patient__first_name')
    date_hierarchy = 'date'