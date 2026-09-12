from django.contrib import admin

from .models import (CenterConfig, Company, Staff, ExchangeRate,
                     LabExam, LabSplitConfig, HomeCareSplitConfig)


@admin.register(CenterConfig)
class CenterConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not CenterConfig.objects.exists()  # un seul enregistrement


admin.site.register(Company)
admin.site.register(Staff)
admin.site.register(ExchangeRate)
admin.site.register(LabExam)
admin.site.register(LabSplitConfig)
admin.site.register(HomeCareSplitConfig)