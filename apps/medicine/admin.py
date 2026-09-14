from django.contrib import admin
from .models import MedicineRecord


@admin.register(MedicineRecord)
class MedicineRecordAdmin(admin.ModelAdmin):
    list_display = ('date', 'patient', 'category', 'prescriber_name', 'amount_original',
                    'currency_original', 'prescriber_amount_usd', 'center_amount_usd', 'status')
    list_filter = ('category', 'status', 'date')
    search_fields = ('patient__last_name', 'patient__first_name', 'prescriber_name')
    date_hierarchy = 'date'