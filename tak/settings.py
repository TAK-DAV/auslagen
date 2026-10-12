import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY or "change-me" in SECRET_KEY:
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY in .env to a long random value. "
        "The placeholder from .env.example must not be used."
    )

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "people.apps.PeopleConfig",
    "masterdata.apps.MasterdataConfig",
    "claims.apps.ClaimsConfig",
    "portal.apps.PortalConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "portal.middleware.StaffOTPVerifiedMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "tak.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "tak.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "auslagen"),
        "USER": os.environ.get("POSTGRES_USER", "auslagen"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "people.Person"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Phone photos from a hut are often larger than Django's 2.5 MB default.
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "portal:login_request"

SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")
LOGIN_TOKEN_PATH = os.environ.get("LOGIN_TOKEN_PATH", "/einreichen/link/{token}/")

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "auslagen@localhost")
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"

# Behind Caddy / any TLS-terminating reverse proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

_csrf = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf.split(",") if o.strip()]
if not CSRF_TRUSTED_ORIGINS and SITE_URL.startswith("https://"):
    CSRF_TRUSTED_ORIGINS = [SITE_URL.rstrip("/")]

if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "0") == "1"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Redirect is handled by Caddy; keep Django's redirect off by default.

# Rate limits (hits per window). Shared across Gunicorn workers via DB cache.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "auslagen_cache",
    }
}
RATELIMIT_MAGIC_LINK_IP = int(os.environ.get("RATELIMIT_MAGIC_LINK_IP", "5"))
RATELIMIT_MAGIC_LINK_EMAIL = int(os.environ.get("RATELIMIT_MAGIC_LINK_EMAIL", "3"))
RATELIMIT_MAGIC_LINK_WINDOW = int(os.environ.get("RATELIMIT_MAGIC_LINK_WINDOW", "3600"))
RATELIMIT_STAFF_LOGIN_IP = int(os.environ.get("RATELIMIT_STAFF_LOGIN_IP", "10"))
RATELIMIT_STAFF_LOGIN_WINDOW = int(os.environ.get("RATELIMIT_STAFF_LOGIN_WINDOW", "3600"))
RATELIMIT_STAFF_TOTP_IP = int(os.environ.get("RATELIMIT_STAFF_TOTP_IP", "20"))
RATELIMIT_STAFF_TOTP_WINDOW = int(os.environ.get("RATELIMIT_STAFF_TOTP_WINDOW", "3600"))

AUTH_LOG_FILE = os.environ.get("AUTH_LOG_FILE", "/var/log/auslagen/auth.log")

_log_handlers = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "auth",
    },
}
_log_handler_names = ["console"]
_auth_log_path = Path(AUTH_LOG_FILE)
try:
    _auth_log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_handlers["auth_file"] = {
        "class": "logging.FileHandler",
        "filename": str(_auth_log_path),
        "formatter": "auth",
    }
    _log_handler_names.append("auth_file")
except OSError:
    pass

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "auth": {
            "format": "%(asctime)s %(levelname)s %(message)s",
        },
    },
    "handlers": _log_handlers,
    "loggers": {
        "auslagen.auth": {
            "handlers": _log_handler_names,
            "level": "INFO",
            "propagate": False,
        },
    },
}
