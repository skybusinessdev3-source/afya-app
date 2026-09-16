"""Settings LOCAL PostgreSQL — pour tester la migration sans toucher à SQLite."""
from .base import *

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('PGNAME', default='afya_db'),
        'USER': env('PGUSER', default='afya_user'),
        'PASSWORD': env('PGPASSWORD', default='afya_secure_2026'),
        'HOST': env('PGHOST', default='localhost'),
        'PORT': env('PGPORT', default='5432'),
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'