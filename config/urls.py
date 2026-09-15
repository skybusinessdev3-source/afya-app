from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core.views import about_page, dashboard, landing, service_worker

urlpatterns = [
    path('sw.js', service_worker, name='sw'),
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('centre/', include('apps.centre.urls')),
    path('patients/', include('apps.patients.urls')),
    path('finance/', include('apps.finance.urls')),
    path('pharmacie/', include('apps.pharmacy.urls')),
    path('laboratoire/', include('apps.laboratory.urls')),
    path('soins-domicile/', include('apps.home_care.urls')),
    path('rendez-vous/', include('apps.appointments.urls')),
    path('rapports/', include('apps.reports.urls')),
    path('messagerie/', include('apps.messaging.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('configuration/', include('apps.settings_app.urls')),
    path('compte/', include('apps.accounts.urls')),
    path('medecine/', include('apps.medicine.urls')),
    path('a-propos/', about_page, name='about'),
    path('', landing, name='landing'),
    path('tableau-de-bord/', dashboard, name='dashboard'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)