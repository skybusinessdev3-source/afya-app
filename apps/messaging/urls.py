from django.urls import path

from . import views

app_name = 'messaging'

urlpatterns = [
    path('', views.messaging_page, name='home'),
    path('api/conversations/', views.api_conversations, name='api_conversations'),
    path('api/messages/<int:conv_id>/', views.api_messages, name='api_messages'),
    path('api/envoyer/<int:conv_id>/', views.api_send, name='api_send'),
    path('api/upload/<int:conv_id>/', views.api_upload, name='api_upload'),
    path('api/nouvelle/', views.api_start_conversation, name='api_start'),
    path('api/groupe/', views.api_create_group, name='api_create_group'),
    path('api/message/<int:msg_id>/supprimer/', views.api_delete_message, name='api_delete_message'),
]