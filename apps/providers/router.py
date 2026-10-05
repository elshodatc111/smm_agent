"""ProviderRouter: ustuvorlik, avtomatik almashtirish (failover), kesh, kredit himoyasi (CONTRACTS §3.1)."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.connections.base import (AuthError, QuotaExceededError, RateLimitError, TransientError)
from apps.core.notify import notify
from apps.core.settings_store import get_setting

from .base import Cost, DataRequest, DataResponse, NoProviderAvailable
from .models import FailoverEvent, ProviderState, ResponseCache
from .quota import (credits_spent, next_pacific_reset, pacific_day_start, record_usage, youtube_quota_pct)

log = logging.getLogger(__name__)
_REGISTRY: dict[str, object] = {}


def register(provider) -> None:
    _REGISTRY[provider.name] = provider


def registry() -> dict:
    if not _REGISTRY:
        from django.conf import settings
        if getattr(settings, "USE_FAKES", False):   # demo/test: tashqi tarmoqqa chiqmaydi
            from .impl import FakeProvider
            for n, u in (("youtube_data_api", "quota_units"), ("scrapecreators", "credits"), ("tme_public", "requests")):
                register(FakeProvider(n, u, 0.0))
            return _REGISTRY
        from .impl import ScrapeCreatorsProvider, TmePublicProvider, YouTubeDataAPIProvider
        for p in (YouTubeDataAPIProvider(), ScrapeCreatorsProvider(), TmePublicProvider()):
            register(p)
    return _REGISTRY


def reset_registry() -> None:
    _REGISTRY.clear()


def _state(name: str) -> ProviderState:
    return ProviderState.objects.get_or_create(name=name)[0]


class ProviderRouter:
    def __init__(self, providers: dict | None = None):
        self.providers = providers if providers is not None else registry()

    # ---- nomzod tekshiruvi ----
    def _skip_reason(self, name: str, req: DataRequest) -> str | None:
        p = self.providers.get(name)
        if p is None:
            return "ro'yxatda yo'q"
        if req.kind not in p.supports.get(req.platform, set()):
            return "bu ma'lumot turini qo'llamaydi"
        if not get_setting(f"providers.{name}.enabled", True):
            return "o'chirilgan"
        st = _state(name)
        if not st.enabled:
            return "o'chirilgan"
        if st.cooldown_until and st.cooldown_until > timezone.now():
            return f"sovitish: {st.cooldown_until:%H:%M}"
        if name == "youtube_data_api" and youtube_quota_pct() >= float(get_setting("providers.quota_switch_pct", 90)):
            return "kunlik kvota chegarasi (%d%%)" % youtube_quota_pct()
        if name == "scrapecreators":
            thr = float(get_setting("scrapecreators.credit_warn_threshold", 20))
            if st.credits_remaining is not None and st.credits_remaining <= thr:
                return "kredit ogohlantirish chegarasidan past"
            now = timezone.now()
            if credits_spent(name, pacific_day_start()) >= float(get_setting("scrapecreators.daily_cap", 50)):
                return "kunlik kredit chegarasi"
            if credits_spent(name, now - timedelta(days=30)) >= float(get_setting("scrapecreators.monthly_cap", 500)):
                return "oylik kredit chegarasi"
        est = p.estimate_cost(req.platform, req.kind, req.limit)
        cap = req.max_cost or (Cost("credits", float(get_setting("scrapecreators.per_run_cap", 10))) if est.unit == "credits" else None)
        if cap and est.unit == cap.unit and est.amount > cap.amount:
            return "bir yig'ish uchun chegaradan oshadi"
        return None

    def _cache_key(self, req: DataRequest) -> str:
        return f"{req.platform}:{req.kind}:{req.target}:{req.limit}:{req.cursor or ''}"

    def fetch(self, req: DataRequest) -> DataResponse:
        age = req.cache_max_age_sec if req.cache_max_age_sec is not None else int(get_setting("scrapecreators.cache_max_age_sec", 21600))
        ck = self._cache_key(req)
        if age:
            row = ResponseCache.objects.filter(key=ck, fetched_at__gte=timezone.now() - timedelta(seconds=age)).first()
            if row:
                return DataResponse("cache", row.data, Cost("credits", 0), True, row.fetched_at)
        order = (get_setting("providers.priority", {}) or {}).get(str(req.platform), [])
        first_failed: str | None = None
        reasons: list[str] = []
        for name in order:
            why = self._skip_reason(name, req)
            if why:
                reasons.append(f"{name}: {why}")
                first_failed = first_failed or name
                continue
            if first_failed and first_failed != name:
                self._log_switch(req, first_failed, name, reasons[-1] if reasons else "")
                first_failed = None
            t0 = timezone.now()
            try:
                resp = self.providers[name].fetch(req)
            except (QuotaExceededError, RateLimitError) as e:
                self._fail(name, req, e, cooldown=getattr(e, "retry_after", None) or 3600)
                reasons.append(f"{name}: {e.code}")
                first_failed = first_failed or name
                continue
            except AuthError as e:
                self._fail(name, req, e, cooldown=6 * 3600)
                reasons.append(f"{name}: auth")
                first_failed = first_failed or name
                continue
            except TransientError as e:
                self._fail(name, req, e, cooldown=300)
                reasons.append(f"{name}: transient")
                first_failed = first_failed or name
                continue
            ms = (timezone.now() - t0).total_seconds() * 1000
            self._ok(name, req, resp, ms)
            ResponseCache.objects.update_or_create(key=ck, defaults={"data": resp.data, "fetched_at": timezone.now()})
            return resp
        retry_at = next_pacific_reset()
        notify("quota.exhausted", "Ma'lumot provayderlari mavjud emas",
               "; ".join(reasons)[:500] + " — vazifa ertaga davom ettiriladi.", severity="warn",
               dedupe_key=f"noprov:{req.platform}:{timezone.now():%Y%m%d%H}")
        raise NoProviderAvailable("; ".join(reasons), retry_at)

    # ---- hisob-kitob ----
    def _ok(self, name, req, resp, ms):
        st = _state(name)
        st.last_ok_at = timezone.now()
        st.avg_latency_ms = ms if st.avg_latency_ms is None else 0.8 * st.avg_latency_ms + 0.2 * ms
        if name == "scrapecreators":
            rem = getattr(self.providers[name], "_last_remaining", None)
            if rem is not None:
                st.credits_remaining = float(rem)
            elif st.credits_remaining is not None and not resp.from_cache:
                st.credits_remaining = max(0.0, st.credits_remaining - resp.cost.amount)
            if st.credits_remaining is not None and st.credits_remaining <= float(get_setting("scrapecreators.credit_warn_threshold", 20)):
                notify("quota.warning", "ScrapeCreators krediti kam", f"Qoldiq: {st.credits_remaining:.0f}", severity="warn",
                       dedupe_key="sc-low")
        st.save()
        if name != "youtube_data_api":  # YouTube kvotasi connector/impl ichida emas, shu yerda yoziladi
            pass
        record_usage(name, units=resp.cost.amount, kind="api", target=req.target, unit_type=resp.cost.unit,
                     from_cache=resp.from_cache, latency_ms=ms, note=str(req.kind))

    def _fail(self, name, req, err, cooldown: int):
        st = _state(name)
        st.last_error, st.last_error_at = str(err)[:300], timezone.now()
        st.cooldown_until = timezone.now() + timedelta(seconds=cooldown)
        st.save()
        record_usage(name, units=0, kind="api", target=req.target, ok=False, error=str(err), note=getattr(err, "code", ""))
        log.warning("provayder %s xato: %s", name, err)

    def _log_switch(self, req, frm, to, reason):
        FailoverEvent.objects.create(platform=str(req.platform), kind=str(req.kind), from_provider=frm, to_provider=to, reason=reason[:200])
        notify("provider.switched", f"Provayder almashdi: {frm} → {to}", reason, dedupe_key=f"switch:{frm}:{to}")
