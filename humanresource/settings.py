"""
Django settings for humanresource project.
Updated: real Gmail SMTP email backend + environment variable security.

SETUP STEPS BEFORE RUNNING:
1. pip install python-decouple
2. Create a file called  .env  next to manage.py
3. Paste your secrets into .env  (see bottom of this file for the template)
4. Add .env to your .gitignore — never commit it
"""

from pathlib import Path
from decouple import config   # pip install python-decouple

BASE_DIR = Path(__file__).resolve().parent.parent


# ==============================================================================
#  SECURITY
# ==============================================================================
# Read SECRET_KEY from .env — never hardcode it
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1',
    cast=lambda v: [h.strip() for h in v.split(',')]
)


# ==============================================================================
#  INSTALLED APPS
# ==============================================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',   # pip install djangorestframework
    'hr',
]


# ==============================================================================
#  MIDDLEWARE
# ==============================================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ==============================================================================
#  URLS & WSGI
# ==============================================================================
ROOT_URLCONF  = 'humanresource.urls'
WSGI_APPLICATION = 'humanresource.wsgi.application'


# ==============================================================================
#  TEMPLATES
# ==============================================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],   # project-level templates folder
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.debug',
            ],
        },
    },
]


# ==============================================================================
#  DATABASE  (Supabase PostgreSQL — your existing config, now from .env)
# ==============================================================================
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     config('DB_NAME',     default='postgres'),
        'USER':     config('DB_USER',     default='postgres.wsphdggpbospllnyqevv'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST':     config('DB_HOST',     default='aws-0-eu-west-1.pooler.supabase.com'),
        'PORT':     config('DB_PORT',     default='5432'),
        'OPTIONS': {
            # keeps Supabase connection alive through the pooler
            'connect_timeout': 10,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
        },
    }
}


# ==============================================================================
#  PASSWORD VALIDATION
# ==============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ==============================================================================
#  INTERNATIONALISATION
# ==============================================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Africa/Addis_Ababa'   # ACT is in Addis Ababa — corrected from UTC
USE_I18N      = True
USE_TZ        = True


# ==============================================================================
#  STATIC & MEDIA FILES
# ==============================================================================
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'   # where collectstatic writes to
MEDIA_URL   = '/media/'
MEDIA_ROOT  = BASE_DIR / 'media'


# ==============================================================================
#  DEFAULT PRIMARY KEY
# ==============================================================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ==============================================================================
#  EMAIL  ← THIS IS THE FIX
#  Using Gmail SMTP via an App Password (not your real Gmail password).
#
#  How to get a Gmail App Password:
#  1. Go to https://myaccount.google.com/security
#  2. Turn on 2-Step Verification (required)
#  3. Go to https://myaccount.google.com/apppasswords
#  4. Create a new app password → name it "ACT HRMS"
#  5. Copy the 16-character code Google gives you
#  6. Paste it into EMAIL_HOST_PASSWORD in your .env file
# ==============================================================================
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = 'smtp.gmail.com'
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True                # TLS on port 587 — required by Gmail
EMAIL_USE_SSL       = False               # never use both TLS and SSL together

EMAIL_HOST_USER     = config('EMAIL_HOST_USER',     default='')   # your Gmail address
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')   # 16-char App Password

DEFAULT_FROM_EMAIL  = config(
    'DEFAULT_FROM_EMAIL',
    default='ACT HRMS <noreply@gmail.com>'
)

# ── Fallback: if EMAIL settings are missing, log to terminal instead of crashing
EMAIL_FAIL_SILENTLY = False   # set True only in production if you want silent failures

# ── Quick switch: set EMAIL_BACKEND_OVERRIDE=console in .env to log during dev
_email_override = config('EMAIL_BACKEND_OVERRIDE', default='')
if _email_override == 'console':
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# ==============================================================================
#  DJANGO REST FRAMEWORK
# ==============================================================================
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon':    '1000/day',
        'qr_scan': '10/min',   # scanner kiosk: max 10 scans/min per IP
    },
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
}


# ==============================================================================
#  LOGIN REDIRECT
# ==============================================================================
LOGIN_URL          = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/hr/'
LOGOUT_REDIRECT_URL = '/login/'


# ==============================================================================
#  SESSION SECURITY
# ==============================================================================
SESSION_COOKIE_AGE      = 28800    # 8 hours — auto-logout after a working day
SESSION_EXPIRE_AT_BROWSER_CLOSE = True


