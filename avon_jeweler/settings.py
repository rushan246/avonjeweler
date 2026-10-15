import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

IS_VERCEL = (
    os.getenv("VERCEL", "").lower() in {"1", "true", "yes"}
    or any(
        os.getenv(name, "").strip()
        for name in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_ENV", "VERCEL_PROJECT_PRODUCTION_URL")
    )
)
DEBUG = not IS_VERCEL and os.getenv("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes"}
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY before running AVON JEWELER with DEBUG disabled.")
    SECRET_KEY = "insecure-development-only-key"
if not DEBUG and SECRET_KEY == "replace-with-a-long-random-secret":
    raise ImproperlyConfigured("Replace the example DJANGO_SECRET_KEY before deploying AVON JEWELER.")


def _host_from_environment(value):
    value = value.strip()
    parsed = urlsplit(value if "://" in value else f"//{value}")
    host = parsed.hostname
    return host.lower() if host else ""


def _vercel_deployment_hosts(environ):
    hosts = []
    for name in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        host = _host_from_environment(environ.get(name, ""))
        if host and host not in hosts:
            hosts.append(host)
    return hosts


ALLOWED_HOSTS = [
    _host_from_environment(host)
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if _host_from_environment(host)
]
DEPLOYMENT_HOST_ENV = os.getenv("DJANGO_DEPLOYMENT_HOSTS", "").strip()
DEPLOYMENT_HOSTS = [
    _host_from_environment(host)
    for host in DEPLOYMENT_HOST_ENV.split(",")
    if _host_from_environment(host)
]
for host in DEPLOYMENT_HOSTS:
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)
VERCEL_DEPLOYMENT_HOSTS = []
if IS_VERCEL:
    VERCEL_DEPLOYMENT_HOSTS = _vercel_deployment_hosts(os.environ)
    for host in VERCEL_DEPLOYMENT_HOSTS:
        if host and host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

CSRF_TRUSTED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
CSRF_TRUSTED_ORIGINS.extend(f"https://{host}" for host in DEPLOYMENT_HOSTS)
CSRF_TRUSTED_ORIGINS.extend(f"https://{host}" for host in VERCEL_DEPLOYMENT_HOSTS)
if IS_VERCEL:
    vercel_url = os.getenv("VERCEL_URL", "").strip()
    if vercel_url and f"https://{vercel_url}" not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(f"https://{vercel_url}")

SECURE_SSL_REDIRECT = IS_VERCEL or os.getenv("DJANGO_SECURE_SSL_REDIRECT", "False").lower() in {"1", "true", "yes"}
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000" if IS_VERCEL else "0"))
if IS_VERCEL:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "store.apps.StoreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "avon_jeweler.urls"
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
                "store.context_processors.store_settings",
            ],
        },
    }
]
WSGI_APPLICATION = "avon_jeweler.wsgi.application"

database_url = os.getenv("DATABASE_URL", "").strip()
if database_url:
    parsed_database_url = urlsplit(database_url)
    if parsed_database_url.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured("DATABASE_URL must use the PostgreSQL postgres:// or postgresql:// scheme.")
    database_options = parse_qs(parsed_database_url.query)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed_database_url.path.lstrip("/")),
            "USER": unquote(parsed_database_url.username or ""),
            "PASSWORD": unquote(parsed_database_url.password or ""),
            "HOST": parsed_database_url.hostname or "",
            "PORT": str(parsed_database_url.port or 5432),
            "OPTIONS": {
                key: values[-1]
                for key, values in database_options.items()
                if key in {"sslmode", "application_name"}
            },
            "CONN_MAX_AGE": 0 if IS_VERCEL else 60,
        }
    }
elif os.getenv("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.getenv("DB_USER", "root"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
            "CONN_MAX_AGE": 0 if IS_VERCEL else 60,
        }
    }
else:
    if IS_VERCEL or not DEBUG:
        raise ImproperlyConfigured(
            "Configure DATABASE_URL (PostgreSQL) or DB_NAME and MySQL credentials before deploying."
        )
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in {"1", "true", "yes"}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() in {"1", "true", "yes"}
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "orders@avonjeweler.example")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
ORDER_NOTIFICATION_EMAIL = os.getenv("ORDER_NOTIFICATION_EMAIL", "").strip()
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_VERIFY_SERVICE_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID", "").strip()
