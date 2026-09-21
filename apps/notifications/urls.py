from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('api/lire-tout/', views.mark_all_read, name='mark_all_read'),
    path('api/non-lues/', views.api_unread, name='api_unread'),
    path('api/push/abonner/', views.push_subscribe, name='push_subscribe'),
    path('api/push/retirer/', views.push_unsubscribe, name='push_unsubscribe'),
]