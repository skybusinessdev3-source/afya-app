from django.urls import path

from . import views

app_name = 'centre'

urlpatterns = [
    path('', views.centre_day, name='day'),
    path('api/recherche-patients/', views.patient_search, name='patient_search'),
    path('api/enregistrer-seance/', views.register_session, name='register_session'),
]