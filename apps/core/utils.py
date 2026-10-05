from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

UZ_MONTHS = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
             "sentabr", "oktabr", "noyabr", "dekabr"]


def tz() -> ZoneInfo:
    from apps.core.settings_store import get_setting
    return ZoneInfo(get_setting("general.timezone", settings.DISPLAY_TZ))


def local(dt: datetime | None) -> datetime | None:
    return timezone.localtime(dt, tz()) if dt else None


def fmt_dt(dt: datetime | None) -> str:
    d = local(dt)
    return f"{d.day} {UZ_MONTHS[d.month]} {d.year}, {d:%H:%M}" if d else "—"


def fmt_num(n) -> str:
    if n is None:
        return "—"
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n)


def now():
    return timezone.now()
