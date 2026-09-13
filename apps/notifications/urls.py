from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('api/lire-tout/', views.mark_all_read, name='mark_all_read'),
]