"""
Django Settings for MedQueue Project
=====================================
Clean, organized, no duplicates.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# BASE & ENV
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# ─────────────────────────────────────────────
# SECURITY
# ─────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-b&t99-v&mfml4b7t2(*o-0f5m$1et%und*qw822fhj!=xve&w2")
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1","medbackend-zvhu.onrender.com").split(",")


# ─────────────────────────────────────────────
# APPLICATIONS
# ─────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_celery_beat",

    # Local apps
    "accounts",
    "booking",
    "payments",
]


# ─────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ─────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True


CORS_ALLOWED_ORIGINS = [
    "https://medque.vercel.app",  # your Vercel frontend URL
    "http://localhost:5173",
    "http://localhost:3000",
]


# ─────────────────────────────────────────────
# URL / WSGI
# ─────────────────────────────────────────────

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# ─────────────────────────────────────────────
# TEMPLATES
# ─────────────────────────────────────────────

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "postgres"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "6543"),
        "OPTIONS": {
            "sslmode": "require",  # ✅ already correct for Supabase
        },
    }
}

# ─────────────────────────────────────────────
# PASSWORD VALIDATION
# ─────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ─────────────────────────────────────────────
# INTERNATIONALIZATION
# ─────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# ─────────────────────────────────────────────
# STATIC & MEDIA
# ─────────────────────────────────────────────

STATIC_URL = "/static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─────────────────────────────────────────────
# REST FRAMEWORK
# ─────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}


# ─────────────────────────────────────────────
# EMAIL (Gmail SMTP)
# ─────────────────────────────────────────────

EMAIL_BACKEND       = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST          = "smtp.gmail.com"
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL  = os.getenv("EMAIL_HOST_USER", "no-reply@medqueue.com")


# ─────────────────────────────────────────────
# CELERY
# ─────────────────────────────────────────────

CELERY_BROKER_URL         = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND     = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_TIMEZONE           = "Asia/Kolkata"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SERIALIZER    = "json"
CELERY_RESULT_SERIALIZER  = "json"
CELERY_ACCEPT_CONTENT     = ["json"]

# ── Development mode: run tasks inline, no Redis/worker needed ──
CELERY_TASK_ALWAYS_EAGER    = True
CELERY_TASK_EAGER_PROPAGATES = True

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "morning-reminders": {
        "task": "booking.tasks.send_session_reminders",
        "schedule": crontab(hour=9, minute=30),
        "args": ["morning"],
    },
    "evening-reminders": {
        "task": "booking.tasks.send_session_reminders",
        "schedule": crontab(hour=14, minute=30),
        "args": ["evening"],
    },
    "recalculate-avg-consult-time": {
        "task": "booking.tasks.recalculate_avg_consult_times",
        "schedule": crontab(minute="*/15", hour="9-17"),
    },
}


# ─────────────────────────────────────────────
# RAZORPAY
# ─────────────────────────────────────────────

RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")


# ─────────────────────────────────────────────
# TWILIO (OTP / SMS)
# ─────────────────────────────────────────────

TWILIO_ACCOUNT_SID        = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN         = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER       = os.getenv("TWILIO_PHONE_NUMBER", "+919495959099")
TWILIO_VERIFY_SERVICE_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID")


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
# For production, swap with:
# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.redis.RedisCache",
#         "LOCATION": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"),
#     }
# }


STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"