from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_page, name='daily'),
    path('export-pdf/', views.export_pdf, name='export_pdf'),
    path('export-excel/', views.export_excel, name='export_excel'),
    path('entreprises/', views.entreprises_page, name='entreprises'),
    path('entreprises/excel/', views.entreprise_excel, name='entreprise_excel'),
    path('prescripteurs/', views.prescripteurs_page, name='prescripteurs'),
    path('prescripteurs/<str:key>/', views.prescripteur_detail, name='prescripteur_detail'),
    path('prescripteurs/<str:key>/excel/', views.prescripteur_excel, name='prescripteur_excel'),
    path('prescripteurs/<str:key>/pdf/', views.prescripteur_pdf, name='prescripteur_pdf'),
    path('mois-details/', views.mois_details_page, name='mois_details'),
    path('activite/<str:slug>/', views.activite_page, name='activite'),
    path('activite/<str:slug>/excel/', views.activite_excel, name='activite_excel'),
    path('activite/<str:slug>/pdf/', views.activite_pdf, name='activite_pdf'),
]