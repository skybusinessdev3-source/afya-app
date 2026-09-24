from django.urls import path
from . import views

app_name = 'medicine'

urlpatterns = [
    path('generale/', views.general_page, name='general'),
    path('manuelle/', views.manual_page, name='manual'),
    path('api/enregistrer/', views.record_create, name='record_create'),
    path('api/part-prescripteur/', views.med_prescriber_paid, name='prescriber_paid'),
]