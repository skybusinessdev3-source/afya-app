from django.urls import path

from . import views

app_name = 'settings_app'

urlpatterns = [
    path('', views.settings_page, name='home'),
    path('api/centre/', views.center_update, name='center_update'),
    path('api/centre-logo/', views.center_logo, name='center_logo'),
    path('api/personnel/', views.staff_create, name='staff_create'),
    path('api/personnel/<int:pk>/basculer/', views.staff_toggle, name='staff_toggle'),
    path('api/taux/', views.rate_create, name='rate_create'),
    path('api/entreprise/', views.company_create, name='company_create'),
    path('api/entreprise/<int:pk>/basculer/', views.company_toggle, name='company_toggle'),
    path('api/entreprise/<int:pk>/creances/', views.company_credit_toggle, name='company_credit_toggle'),
    path('api/repartition-labo/', views.lab_split_create, name='lab_split_create'),
    path('api/repartition-domicile/', views.home_split_create, name='home_split_create'),
    path('api/repartition-medecine/', views.medicine_split_create, name='medicine_split_create'),
    path('api/pourcentage-medecin/', views.prescriber_config_create, name='prescriber_config_create'),
    path('api/pourcentage-medecin/<int:pk>/basculer/', views.prescriber_config_toggle, name='prescriber_config_toggle'),
    path('api/pourcentage-medecin/<int:pk>/supprimer/', views.prescriber_config_delete, name='prescriber_config_delete'),
    path('api/examen/<int:pk>/basculer/', views.exam_toggle, name='exam_toggle'),
    path('api/examen/<int:pk>/modifier/', views.exam_update, name='exam_update'),
    path('api/service/', views.service_create, name='service_create'),
    path('api/service/<int:pk>/basculer/', views.service_toggle, name='service_toggle'),
    path('api/code/', views.code_create, name='code_create'),
    path('api/code/<int:pk>/basculer/', views.code_toggle, name='code_toggle'),
    path('api/service/<int:pk>/modifier/', views.service_update, name='service_update'),
]