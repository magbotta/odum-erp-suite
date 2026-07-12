"""Base settings shared across all environments."""
from __future__ import annotations
from pathlib import Path
from decouple import config, Csv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY")

ALLOWED_HOSTS: list[str] = config("ALLOWED_HOSTS", default="localhost", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    # core — auth must come first (AUTH_USER_MODEL)
    "core.auth.apps.OchreAuthConfig",
    # standard django admin (after custom user model)
    "django.contrib.admin",
    "django.contrib.sessions",
    # core — platform
    "core.audit.apps.OchreAuditConfig",
    # Phase 1 business apps — must be before MetadataEngineConfig so their
    # entity_dir is discovered during MetadataEngineConfig.ready()
    "apps.crm.apps.CRMConfig",
    "apps.hrm.apps.HRMConfig",
    "apps.warehouse.apps.WarehouseConfig",
    "apps.accounting.apps.AccountingConfig",
    "apps.purchasing.apps.PurchasingConfig",
    "apps.sales.apps.SalesConfig",
    # Phase 2 business apps
    "apps.payroll.apps.PayrollConfig",
    "apps.project.apps.ProjectConfig",
    "apps.asset_management.apps.AssetManagementConfig",
    "apps.website.apps.WebsiteConfig",
    # Phase 3 industry apps
    "apps.manufacturing.apps.ManufacturingConfig",
    "apps.pos.apps.POSConfig",
    # Phase 4 industry apps
    "apps.education_sis.apps.EducationSISConfig",
    "apps.healthcare_his.apps.HealthcareHISConfig",
    "apps.agriculture.apps.AgricultureConfig",
    "apps.nonprofit.apps.NonprofitConfig",
    "apps.telecom.apps.TelecomConfig",
    "apps.government.apps.GovernmentConfig",
    "apps.microfinance.apps.MicrofinanceConfig",
    "apps.legal_services.apps.LegalServicesConfig",
    # core — document numbering
    "core.numbering.apps.NumberingConfig",
    # metadata engine scans entity dirs from apps above
    "core.metadata_engine.apps.MetadataEngineConfig",
    "core.platform_api.apps.PlatformAPIConfig",
    # third-party
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
]

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
    "core.audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---
DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        default="postgres://ochre:ochre@localhost:5432/ochre",
        conn_max_age=60,
        conn_health_checks=True,
    )
}

# --- Cache / Celery ---
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_RESULT_EXTENDED = True

# --- Auth ---
AUTH_USER_MODEL = "ochre_auth.OchreUser"

AUTHENTICATION_BACKENDS = [
    "core.auth.backends.JWTBackend",
    "core.auth.backends.APIKeyBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

JWT_ACCESS_TOKEN_LIFETIME_MINUTES = config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60, cast=int)
JWT_REFRESH_TOKEN_LIFETIME_DAYS = config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
JWT_ALGORITHM = "HS256"

# --- CORS ---
CORS_ALLOWED_ORIGINS: list[str] = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://localhost:5173",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# --- Internationalization ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# --- Media files ---
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Email ---
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@odum.local")

# --- Default primary key ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Odum ERP Suite-specific ---
OCHRE_ENTITY_SCAN_DIRS: list[str] = []  # populated by each App's AppConfig
