from django.contrib import admin

from .models import LaboratoryRecord


@admin.register(LaboratoryRecord)
class LaboratoryRecordAdmin(admin.ModelAdmin):
    list_display = ('date', 'patient', 'exam', 'prescriber_name', 'amount_original',
                    'currency_original', 'prescriber_amount_usd',
                    'lab_team_amount_usd', 'center_amount_usd', 'status')
    list_filter = ('status', 'date', 'exam')
    search_fields = ('patient__last_name', 'patient__first_name', 'exam__name', 'prescriber_name')
    date_hierarchy = 'date'