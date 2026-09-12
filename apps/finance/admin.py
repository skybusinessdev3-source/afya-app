from django.contrib import admin

from .models import Expense, Invoice, Payment


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('reference', 'patient', 'label', 'amount_original', 'currency_original',
                    'amount_usd', 'status', 'date')
    list_filter = ('status', 'currency_original', 'date')
    search_fields = ('reference', 'label', 'patient__last_name', 'patient__first_name')
    date_hierarchy = 'date'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'amount_original', 'currency_original', 'amount_usd',
                    'rate_used', 'method', 'status', 'date', 'received_by')
    list_filter = ('status', 'currency_original', 'method', 'date')
    search_fields = ('invoice__reference', 'invoice__patient__last_name')
    date_hierarchy = 'date'


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('label', 'amount_original', 'currency_original', 'amount_usd',
                    'person', 'date', 'created_by')
    list_filter = ('currency_original', 'date')
    search_fields = ('label', 'person_other')
    date_hierarchy = 'date'