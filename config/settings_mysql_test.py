from .settings_test import *  # noqa

# MySQL/MariaDB'ga qarshi test: DB_* o'zgaruvchilari bilan (tools/test_mysql.py ishlatadi)
import pymysql
pymysql.install_as_MySQLdb()
DATABASES = {"default": {"ENGINE": "django.db.backends.mysql", "NAME": env("DB_NAME", "smm_platform"), "USER": env("DB_USER", "smm"),
                         "PASSWORD": env("DB_PASSWORD"), "HOST": env("DB_HOST", "127.0.0.1"), "PORT": env("DB_PORT", "3306"),
                         "OPTIONS": {"charset": "utf8mb4"}, "TEST": {"NAME": "test_" + env("DB_NAME", "smm_platform"), "CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"}}}
