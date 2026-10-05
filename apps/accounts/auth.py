"""Kirish: lockout bilan."""
from datetime import timedelta

from django.contrib.auth import authenticate
from django.utils import timezone

from apps.core.audit import audit
from apps.core.settings_store import get_setting

from .models import User


class LockedOut(Exception):
    pass


def login_check(request, username: str, password: str):
    u = User.objects.filter(username=username).first()
    if u and u.locked_until and u.locked_until > timezone.now():
        raise LockedOut("Urinishlar ko'p. Birozdan keyin qayta urinib ko'ring.")
    user = authenticate(request, username=username, password=password)
    if user is None:
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
    audit("auth.login", user=user)
    return user
