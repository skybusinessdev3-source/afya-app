from django.urls import path

from . import views

app_name = 'patients'

urlpatterns = [
    path('', views.patient_list, name='list'),
    path('<int:pk>/', views.patient_detail, name='detail'),
    path('api/nouveau/', views.patient_create, name='create'),
    path('<int:pk>/modifier/', views.patient_update, name='update'),
    path('<int:pk>/archiver/', views.patient_toggle_active, name='toggle_active'),
]