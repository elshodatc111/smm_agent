"""Kirish: lockout bilan."""
from datetime import timedelta

from django.contrib.auth import authenticate
from django.utils import timezone

from apps.core.audit import audit
from apps.core.settings_store import get_setting

from .models import User


class LockedOut(Exception):
    pass


IP_LIMIT, IP_WINDOW = 20, 900   # 15 daqiqada bitta IP dan 20 ta xato urinish


def client_ip(request) -> str:
    from django.conf import settings
    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):   # Nginx ortida
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "?"


def _ip_key(request) -> str:
    return "loginfail:" + client_ip(request)


def login_check(request, username: str, password: str):
    from django.core.cache import cache
    if int(cache.get(_ip_key(request), 0)) >= IP_LIMIT:
        raise LockedOut("Bu manzildan urinishlar ko'p. Birozdan keyin qayta urinib ko'ring.")
    u = User.objects.filter(username=username).first()
    if u and u.locked_until and u.locked_until > timezone.now():
        raise LockedOut("Urinishlar ko'p. Birozdan keyin qayta urinib ko'ring.")
    user = authenticate(request, username=username, password=password)
    if user is None:
        k = _ip_key(request)
        cache.add(k, 0, IP_WINDOW)
        try:
            cache.incr(k)
        except ValueError:
            cache.set(k, 1, IP_WINDOW)
        if u:
            u.failed_attempts += 1
            if u.failed_attempts >= int(get_setting("security.lockout_attempts", 5)):
                u.locked_until = timezone.now() + timedelta(minutes=int(get_setting("security.lockout_minutes", 15)))
                u.failed_attempts = 0
                audit("auth.lockout", user=u)
            u.save(update_fields=["failed_attempts", "locked_until"])
        audit("auth.failed", target=username)
        return None
    if user.failed_attempts or user.locked_until:
        user.failed_attempts, user.locked_until = 0, None
        user.save(update_fields=["failed_attempts", "locked_until"])
    cache.delete(_ip_key(request))
    audit("auth.login", user=user)
    return user
