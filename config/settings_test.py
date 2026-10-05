from .settings import *  # noqa

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
USE_FAKES = True
FERNET_KEYS = ["IIftQ7Oi7_BAc9FculIZvBe12Wlm8e_6g-l9jnSVFaE="]
LOGGING = {"version": 1, "disable_existing_loggers": False}
import tempfile as _t
MEDIA_ROOT = _t.mkdtemp(prefix="smm_media_")
