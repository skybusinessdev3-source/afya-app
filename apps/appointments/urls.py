from django.urls import path

from . import views

app_name = 'appointments'

urlpatterns = [
    path('', views.calendar_page, name='calendar'),
    path('api/mois/', views.month_appointments, name='month'),
    path('api/nouveau/', views.appointment_create, name='create'),
    path('api/annuler/<int:pk>/', views.appointment_cancel, name='cancel'),
]