from django.contrib import admin

from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'sex', 'company', 'phone',
                    'sessions_prescribed', 'sessions_done', 'sessions_remaining', 'day_pattern')
    search_fields = ('last_name', 'middle_name', 'first_name', 'phone')
    list_filter = ('sex', 'day_pattern', 'company')