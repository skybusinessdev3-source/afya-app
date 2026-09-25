from django.urls import path

from . import views

app_name = 'home_care'

urlpatterns = [
    path('', views.home_care_page, name='home'),
    path('api/enregistrer/', views.home_care_create, name='create'),
    path('api/statut-patient/', views.patient_status, name='patient_status'),
    path('api/part-medecin/', views.home_doctor_paid, name='doctor_paid'),
]