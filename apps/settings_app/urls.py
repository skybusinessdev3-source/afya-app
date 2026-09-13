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
    path('api/repartition-labo/', views.lab_split_create, name='lab_split_create'),
    path('api/repartition-domicile/', views.home_split_create, name='home_split_create'),
    path('api/examen/<int:pk>/basculer/', views.exam_toggle, name='exam_toggle'),
    path('api/examen/<int:pk>/modifier/', views.exam_update, name='exam_update'),
    path('api/service/', views.service_create, name='service_create'),
    path('api/service/<int:pk>/basculer/', views.service_toggle, name='service_toggle'),
]