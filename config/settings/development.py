from .base import *

DEBUG = True

# SQLite — local uniquement. 'timeout' évite le "database is locked"
# quand plusieurs onglets / l'app PWA accèdent en parallèle.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 20},
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'