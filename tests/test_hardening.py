import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.django_db


def test_backoff_grows_and_resets():
    from apps.jobs.worker import Backoff
    b = Backoff(base=5, cap=300)
    waits = [b.fail("x", RuntimeError("e")) for _ in range(9)]
    assert waits[0] == 5 and waits[1] == 10 and max(waits) == 300
    b.ok()
    assert b.n == 0 and b.fail("x", RuntimeError("e")) == 5


def _run_settings(**env):
    e = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
    e.update({"DJANGO_SETTINGS_MODULE": "config.settings", "DB_ENGINE": "sqlite"}, **env)
    return subprocess.run([sys.executable, "-c", "import django.conf as c;c.settings.SECRET_KEY"],
                          env=e, capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))


def test_insecure_settings_refuse_to_start():
    r = _run_settings(SECRET_KEY="change-me", FERNET_KEYS="", ALLOWED_HOSTS="*", DEBUG="0")
    assert r.returncode != 0 and "SECRET_KEY" in r.stderr and "ALLOWED_HOSTS" in r.stderr


def test_secure_settings_start():
    r = _run_settings(SECRET_KEY="k" * 50, FERNET_KEYS="IIftQ7Oi7_BAc9FculIZvBe12Wlm8e_6g-l9jnSVFaE=",
                      ALLOWED_HOSTS="smm.example.uz", DEBUG="0", HTTPS="1")
    assert r.returncode == 0, r.stderr


def test_ip_throttle(rf, settings):
    from django.core.cache import cache
    from apps.accounts import auth
    cache.clear()
    req = rf.post("/kirish/")
    for _ in range(auth.IP_LIMIT):
        assert auth.login_check(req, "nouser", "bad") is None
    with pytest.raises(auth.LockedOut):
        auth.login_check(req, "nouser", "bad")
    cache.clear()
