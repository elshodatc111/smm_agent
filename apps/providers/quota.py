"""Kvota/kredit hisobi. YouTube kvotasi Tinch okeani (Pacific) vaqti bilan tiklanadi."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.utils import timezone

from apps.core.settings_store import get_setting

from .models import ProviderState, ProviderUsageLog

PACIFIC = ZoneInfo("America/Los_Angeles")


def pacific_day_start(now: datetime | None = None) -> datetime:
    n = (now or timezone.now()).astimezone(PACIFIC)
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def next_pacific_reset(now: datetime | None = None) -> datetime:
    return pacific_day_start(now) + timedelta(days=1, minutes=5)


def record_usage(provider: str, *, units: float, kind: str = "", target: str = "", unit_type: str = "quota_units",
                 ok: bool = True, from_cache: bool = False, latency_ms: float | None = None, error: str = "",
                 note: str = "") -> None:
    ProviderUsageLog.objects.create(provider=provider, kind=kind, target=target[:200], units=units, unit_type=unit_type,
                                    ok=ok, from_cache=from_cache, latency_ms=latency_ms, error=error[:300], note=note[:200])


def units_today(provider: str) -> float:
    start = pacific_day_start()
    return ProviderUsageLog.objects.filter(provider=provider, at__gte=start, kind__in=["", "api"], from_cache=False
                                           ).aggregate(s=Sum("units"))["s"] or 0.0


def youtube_quota_used() -> float:
    start = pacific_day_start()
    return ProviderUsageLog.objects.filter(provider="youtube_data_api", at__gte=start, from_cache=False
                                           ).exclude(kind="upload").aggregate(s=Sum("units"))["s"] or 0.0


def youtube_quota_pct() -> float:
    limit = float(get_setting("providers.youtube_data_api.daily_quota", 10000))
    return 100.0 * youtube_quota_used() / limit if limit else 0.0


def record_youtube_upload() -> None:
    ProviderUsageLog.objects.create(provider="youtube_data_api", kind="upload", units=0, note="video upload")


def youtube_uploads_left() -> int:
    start = pacific_day_start()
    used = ProviderUsageLog.objects.filter(provider="youtube_data_api", kind="upload", at__gte=start).count()
    cap = int(get_setting("youtube.upload_daily_cap", 6))
    # kvotadan hisoblangan chegara: (limit - ishlatilgan) // 1600
    quota_left = float(get_setting("providers.youtube_data_api.daily_quota", 10000)) - youtube_quota_used()
    by_quota = int(max(0, quota_left) // 1650)
    return max(0, min(cap - used, by_quota))


def credits_spent(provider: str, since: datetime) -> float:
    return ProviderUsageLog.objects.filter(provider=provider, at__gte=since, unit_type="credits", from_cache=False
                                           ).aggregate(s=Sum("units"))["s"] or 0.0


def days_left(provider: str) -> float | None:
    st = ProviderState.objects.filter(name=provider).first()
    if not st or st.credits_remaining is None:
        return None
    week = credits_spent(provider, timezone.now() - timedelta(days=7)) / 7.0
    return None if week <= 0 else st.credits_remaining / week
