from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from apps.core.views import dashboard

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('centre/', include('apps.centre.urls')),
    path('', dashboard, name='dashboard'),
    path('patients/', include('apps.patients.urls')),
    path('finance/', include('apps.finance.urls')),
    path('pharmacie/', include('apps.pharmacy.urls')),
    path('laboratoire/', include('apps.laboratory.urls')),
    path('soins-domicile/', include('apps.home_care.urls')),
    path('rendez-vous/', include('apps.appointments.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('rapports/', include('apps.reports.urls')),
    path('configuration/', include('apps.settings_app.urls')),
    path('compte/', include('apps.accounts.urls')),
    path('messagerie/', include('apps.messaging.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)