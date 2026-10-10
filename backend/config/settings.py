"""
DREAMZONE — Multilevel (CEFR) learning and mock exam platform.

All secrets and environment-specific values come from environment variables
(loaded from a local .env file in development). See .env.example.
"""
import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# override=True: the dev autoreloader passes the env from first start to every
# reload, so without it edits to .env (keys, SITE_NAME) need a manual restart.
# Hosts such as Render set their own variables (and RENDER=true); a local .env must never override them.
if not os.environ.get("RENDER"):
    load_dotenv(BASE_DIR / ".env", override=True)


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"Environment variable {name} is required.")
    return value


def env_bool(name, default=False):
    return str(os.environ.get(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    return int(os.environ.get(name, default))


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = env("SECRET_KEY", required=not DEBUG) or "dev-only-insecure-key-change-me"
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):  # Render sets this to the service's own hostname
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")
# Behind the Vercel proxy the browser's host is the Vercel domain; trust the forwarded host
# so redirects, CSRF and absolute links use it.
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", False)
CSRF_FAILURE_VIEW = "core.views.csrf_failure"

SITE_NAME = env("SITE_NAME", "DREAMZONE")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    # Local apps
    "core",
    "accounts",
    # Kept only until their tables are dropped (`migrate quizzes zero && migrate courses zero`).
    "courses",
    "quizzes",
    "exams",
    "results",
    "writing",
    "speaking",
    "ai",
    "dashboard",
    "admin_dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves collected static files on Render
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------- DB
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "bandwise"),
        "USER": env("DB_USER", ""),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", ""),
        "PORT": env("DB_PORT", ""),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
    }
}

# Hosted databases (Render, Railway, Neon…) give one URL instead of separate settings.
if env("DATABASE_URL"):
    from urllib.parse import unquote, urlparse

    _db = urlparse(env("DATABASE_URL"))
    DATABASES["default"].update({
        "NAME": unquote(_db.path.lstrip("/")), "USER": unquote(_db.username or ""),
        "PASSWORD": unquote(_db.password or ""), "HOST": _db.hostname or "", "PORT": str(_db.port or ""),
    })

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------------- Auth
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "core:home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ------------------------------------------------------------------------- I18N
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Asia/Tashkent")
USE_I18N = True
USE_TZ = True

# ----------------------------------------------------------- Static and media
STATIC_URL = "/static/"
# The site's own CSS/JS/images live in the frontend project (deployed to Vercel's CDN);
# Django reads them from there so templates and {% static %} keep working everywhere.
FRONTEND_STATIC_DIR = Path(env("FRONTEND_STATIC_DIR", BASE_DIR.parent / "frontend" / "public" / "static"))
STATICFILES_DIRS = [FRONTEND_STATIC_DIR]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Public media (avatars, course thumbnails, task images). Served by the web
# server in production; by Django only when DEBUG=True.
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", BASE_DIR / "media"))

# Private media (speaking recordings, lesson videos/materials, listening audio).
# Never exposed through a public URL — always streamed through permission-checked views.
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", BASE_DIR / "private_media"))
# Optional: nginx "internal" location (e.g. /protected/) that maps to PRIVATE_MEDIA_ROOT.
# When set, Django checks permissions and nginx streams the bytes (X-Accel-Redirect).
PRIVATE_MEDIA_X_ACCEL = env("PRIVATE_MEDIA_X_ACCEL", "")

USE_S3 = env_bool("USE_S3", False)
if USE_S3:
    # Requires `pip install django-storages[s3]`. Private files use signed URLs
    # internally, but are still streamed only through permission-checked views.
    _s3_common = {
        "bucket_name": env("AWS_STORAGE_BUCKET_NAME", required=True),
        "endpoint_url": env("AWS_S3_ENDPOINT_URL") or None,
        "region_name": env("AWS_S3_REGION_NAME") or None,  # "auto" for Cloudflare R2
        "access_key": env("AWS_ACCESS_KEY_ID", required=True),
        "secret_key": env("AWS_SECRET_ACCESS_KEY", required=True),
        "file_overwrite": False,
        "signature_version": "s3v4",
        "default_acl": env("AWS_DEFAULT_ACL") or None,  # R2 has no ACLs: leave empty
    }
    # Public files (pictures, maps, avatars): with a public domain (e.g. an R2 r2.dev URL) plain links,
    # otherwise short-lived signed links, so the bucket itself can stay private.
    _public_domain = env("AWS_S3_CUSTOM_DOMAIN") or None
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage",
                    "OPTIONS": {**_s3_common, "location": "public", "custom_domain": _public_domain,
                                "querystring_auth": not _public_domain, "querystring_expire": 6 * 3600}},
        "private": {"BACKEND": "storages.backends.s3.S3Storage",
                    "OPTIONS": {**_s3_common, "location": "private"}},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "private": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": str(PRIVATE_MEDIA_ROOT), "base_url": None}},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

# ------------------------------------------------------------- Upload limits
# Per-type limits in megabytes (enforced by core.validators).
UPLOAD_LIMITS_MB = {
    "image": env_int("MAX_IMAGE_MB", 5),
    "document": env_int("MAX_DOCUMENT_MB", 25),
    "video": env_int("MAX_VIDEO_MB", 500),
    "audio": env_int("MAX_AUDIO_MB", 60),
    "recording": env_int("MAX_RECORDING_MB", 25),
}
# Files larger than this are streamed to a temp file instead of memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000
FILE_UPLOAD_PERMISSIONS = 0o640

# ----------------------------------------------------------------------- DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", "60/min"),
        "user": env("THROTTLE_USER", "600/min"),
        "auth": env("THROTTLE_AUTH", "10/min"),
        "ai_submit": env("THROTTLE_AI_SUBMIT", "40/hour"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ------------------------------------------------------------------------ AI
# Evaluation (LLM) provider: "anthropic" or "openai".
AI_PROVIDER = env("AI_PROVIDER", "anthropic").lower()
AI_API_KEY = env("AI_API_KEY", "")
AI_MODEL = env("AI_MODEL", "")  # empty -> provider default
AI_EFFORT = env("AI_EFFORT", "high")  # Anthropic only: low|medium|high|xhigh|max
AI_TIMEOUT = env_int("AI_TIMEOUT", 180)
AI_FEEDBACK_LANGUAGE = env("AI_FEEDBACK_LANGUAGE", "English")
AI_EXPLAIN_DAILY_LIMIT = env_int("AI_EXPLAIN_DAILY_LIMIT", 40)  # new "Why?" explanations per student per day
# Speech-to-text provider: "openai" (Whisper / gpt-4o-transcribe).
STT_PROVIDER = env("STT_PROVIDER", "openai").lower()
STT_API_KEY = env("STT_API_KEY", "") or (AI_API_KEY if STT_PROVIDER == AI_PROVIDER else "")
STT_MODEL = env("STT_MODEL", "")  # empty -> provider default (whisper-1 / gemini-3.5-flash)
# How AI jobs run: "thread" (background thread pool in the web process),
# "sync" (inline, blocks the request — useful for tests), or "queue"
# (only via `manage.py process_ai_queue`, e.g. from cron/systemd).
AI_TASK_MODE = env("AI_TASK_MODE", "thread").lower()
AI_WORKERS = env_int("AI_WORKERS", 3)

# ------------------------------------------------------------------- Exams
# Seconds of grace after a timed exam's deadline before answers are frozen.
EXAM_SUBMIT_GRACE_SECONDS = env_int("EXAM_SUBMIT_GRACE_SECONDS", 90)

# --------------------------------------------------------------------- Email
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "DREAMZONE <no-reply@localhost>")

# ------------------------------------------------------------------ Security
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # JS reads it to send X-CSRFToken with fetch()
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
    CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", True)
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
