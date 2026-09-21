from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_page, name='daily'),
    path('export-pdf/', views.export_pdf, name='export_pdf'),
    path('export-excel/', views.export_excel, name='export_excel'),
    path('entreprises/', views.entreprises_page, name='entreprises'),
    path('entreprises/excel/', views.entreprise_excel, name='entreprise_excel'),
]