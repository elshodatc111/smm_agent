
from .env import BASE_DIR, env, env_bool, load_env

load_env()

SECRET_KEY = env("SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "*").split(",")]
USE_FAKES = env_bool("USE_FAKES", False)
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
FERNET_KEYS = [k.strip() for k in env("FERNET_KEYS", "").split(",") if k.strip()]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.businesses",
    "apps.connections",
    "apps.providers",
    "apps.ai_router",
    "apps.jobs",
    "apps.metrics",
    "apps.content",
    "apps.studio",
    "apps.media_analysis",
    "apps.ads",
    "apps.goals",
    "apps.facts",
    "apps.links",
    "apps.reports",
    "apps.tgbot",
    "apps.health",
    "apps.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.accounts.middleware.BusinessContextMiddleware",
    "apps.accounts.middleware.TimezoneMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "apps.web.context.ui_context",
    ]},
}]

if env("DB_ENGINE", "mysql") == "sqlite":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3",
                             "OPTIONS": {"timeout": 60, "transaction_mode": "IMMEDIATE",
                                         "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=60000;"}}}
else:
    import pymysql
    pymysql.install_as_MySQLdb()
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.mysql", "NAME": env("DB_NAME", "smm_platform"),
        "USER": env("DB_USER", "smm"), "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", "127.0.0.1"), "PORT": env("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"}, "CONN_MAX_AGE": 60,
    }}

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
LOGIN_URL = "/kirish/"
LOGIN_REDIRECT_URL = "/"
LANGUAGE_CODE = "uz"
TIME_ZONE = "UTC"
DISPLAY_TZ = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_STORE = BASE_DIR / "media_store"
MEDIA_ROOT = MEDIA_STORE
MEDIA_TMP = BASE_DIR / "media_tmp"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_AGE = 12 * 3600
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler",
}

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "filters": {"secrets": {"()": "apps.core.logging_utils.SecretFilter"}},
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["secrets"]},
        "file": {"class": "logging.handlers.RotatingFileHandler", "filename": str(LOG_DIR / "app.log"),
                 "maxBytes": 5_000_000, "backupCount": 10, "encoding": "utf-8",
                 "formatter": "plain", "filters": ["secrets"]},
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}

WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_USE_FINDERS = True   # collectstatic shart emas: static/ papkadan to'g'ridan-to'g'ri
