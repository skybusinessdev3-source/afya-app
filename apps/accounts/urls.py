from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_page, name='register'),
    path('api/register/', views.register, name='register_submit'),
    path('profil/', views.profile_page, name='profile'),
    path('api/profil/', views.profile_update, name='profile_update'),
    path('api/profil/avatar/', views.profile_avatar, name='profile_avatar'),
    path('api/profil/mot-de-passe/', views.profile_password, name='profile_password'),
]