from django.contrib import admin

from .models import PharmacyProduct, PharmacySale, StockMovement


@admin.register(PharmacyProduct)
class PharmacyProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_usd', 'price_fc', 'stock_available', 'expiry_date', 'is_active')
    search_fields = ('name',)
    list_filter = ('is_active',)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('product', 'movement_type', 'quantity', 'date', 'reason', 'status')
    list_filter = ('movement_type', 'status', 'date')


@admin.register(PharmacySale)
class PharmacySaleAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'total_usd', 'total_fc', 'patient', 'date')
    search_fields = ('product__name', 'patient__last_name')