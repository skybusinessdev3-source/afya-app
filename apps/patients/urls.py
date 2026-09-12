from django.urls import path

from . import views

app_name = 'patients'

urlpatterns = [
    path('api/nouveau/', views.patient_create, name='create'),
]