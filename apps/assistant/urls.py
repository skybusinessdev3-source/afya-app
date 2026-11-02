from django.urls import path

from . import views

app_name = 'assistant'

urlpatterns = [
    path('', views.assistant_page, name='home'),
    path('api/chat/', views.api_chat, name='api_chat'),
    path('api/envoyer-fichier/', views.api_upload, name='api_upload'),
    path('api/confirmer/', views.api_confirm, name='api_confirm'),
    path('fichier/<int:message_id>/', views.download, name='download'),
]
