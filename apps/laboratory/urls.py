from django.urls import path

from . import views

app_name = 'laboratory'

urlpatterns = [
    path('', views.lab_page, name='home'),
    path('api/enregistrer/', views.lab_record_create, name='record_create'),
    path('api/nouveau-examen/', views.lab_exam_create, name='exam_create'),
]