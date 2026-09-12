from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('datetime', 'patient', 'doctor', 'motif', 'status', 'remind_days_before', 'alarm')
    list_filter = ('status', 'datetime', 'doctor')
    search_fields = ('patient__last_name', 'patient__first_name', 'motif')
    date_hierarchy = 'datetime'