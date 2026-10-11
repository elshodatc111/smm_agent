"""Sozlamalar ombori. Koddagi DEFAULTS faqat sukut qiymat; haqiqiy qiymat bazadan."""
from __future__ import annotations

import copy
from typing import Any

from django.core.cache import cache

from . import crypto

DEFAULTS: dict[str, Any] = {
    "general.system_name": "SMM Platforma",
    "general.theme_default": "light",
    "general.brand_color": "#E11D2E",
    "general.timezone": "Asia/Tashkent",
    "general.public_url": "",
    "agency.max_businesses": 10,
    "general.agency_logo": "",
    "collect.schedule": ["08:00", "12:00", "17:00", "21:00"],
    "collect.history_days": 365,
    "collect.story_snapshot_minutes": 60,
    "ideas.per_day": 1,
    "ideas.daily_enabled": True,
    "client.publish_notice": True,
    "collect.story_deep_after_hours": 20,
    "collect.story_deep_minutes": 20,
    "collect.post_metric_windows": ["1h", "6h", "24h", "72h", "7d", "30d"],
    "collect.enabled": True,
    "providers.priority": {"youtube": ["youtube_data_api", "scrapecreators"],
                           "instagram": ["scrapecreators"], "telegram": ["tme_public", "scrapecreators"]},
    "providers.quota_switch_pct": 90,
    "providers.youtube_data_api.daily_quota": 10000,
    "providers.youtube_data_api.enabled": True,
    "providers.scrapecreators.enabled": True,
    "scrapecreators.mode": "free",
    "scrapecreators.credit_warn_threshold": 20,
    "scrapecreators.per_run_cap": 10,
    "scrapecreators.daily_cap": 50,
    "scrapecreators.monthly_cap": 500,
    "scrapecreators.cache_max_age_sec": 21600,
    "competitors.light_per_day": 3,
    "competitors.heavy_per_week": 1,
    "telethon.daily_request_cap": 400,
    "telethon.min_delay_sec": 3,
    "telethon.max_delay_sec": 9,
    "telethon.max_consecutive_errors": 3,
    "telethon.active_hours": ["08:00", "23:00"],
    "ai.primary": "openai",              # asosiy provayder: openai | claude
    "ai.fallback": "auto",               # auto = ikkinchisi zaxira (kaliti bo'lsa) | none
    "ai.task.long_uz": "auto", "ai.task.classify": "auto", "ai.task.vision": "auto", "ai.task.brand_profile": "auto",
    "ai.task.script_review": "auto", "ai.task.comment_reply": "auto", "ai.task.why_worked": "auto", "ai.task.ad_plan": "auto",
    "ai.models": {"claude": "claude-sonnet-4-5", "openai": "gpt-4o-mini", "openai_stt": "whisper-1"},
    "ai.openai.model_complex": "gpt-4o",  # murakkab vazifalar (ssenariy, reja, brend, reklama) uchun kuchliroq model
    "ai.claude.model_complex": "",        # bo'sh = oddiy Claude modeli
    "ai.cache.default_ttl_sec": 86400,
    "ai.limits": {},
    "stt.uz_prompt": "Bu o'zbek tilidagi nutq. Lotin alifbosida yozing.",
    "stt.min_confidence": 0.55,
    "publish.use_r2": "auto",
    "publish.r2.max_gb": 9,
    "publish.r2.lead_min": 45,
    "publish.r2.keep_failed_hours": 24,
    "cloud.auto_upload": True,          # media fayllar saqlanganda Cloudflare'ga ham yuklansin
    "cloud.retention": "manual",        # manual = faqat qo'lda o'chiriladi; after_publish = nashrdan keyin o'chadi
    "cloud.sweep_orphans": False,       # bucketdagi bazada yo'q fayllarni o'chirish (xavfli, o'chiq)
    "publish.late_policy_min": 30,
    "publish.max_attempts": 3,
    "youtube.upload_daily_cap": 6,
    "jobs.workers": {"publish": 2, "collect": 3, "ai": 2, "media": 1, "system": 1},
    "jobs.lock_timeout_min": 10,
    "jobs.media_lock_timeout_min": 60,
    "notify.mandatory": ["publish.failed", "token.expiring", "quota.exhausted"],
    "notify.dedupe_minutes": 30,
    "security.session_hours": 12,
    "security.lockout_attempts": 5,
    "security.lockout_minutes": 15,
    "reports.brand_color": "#E11D2E",
    "reports.logo": "",
    "reports.auto_send_requires_approval": False,
    "media.retention_days": 90,
    "media.local_whisper_model": "small",
    "ads.min_age_hours": 24,
    "facts.per_topic_per_day": 2,
    "facts.max_age_days": 21,
    "facts.sources_per_run": 25,
    "facts.allow_untranslated": True,
    "analytics.winner_multiplier": 1.5,
    "analytics.anomaly_z": 2.5,
    "backup.keep_days": 14,
    "backup.dir": "backups",
    "worker.cloudflare_url": "", "worker.admin_token": "",
    "meta.app_id": "", "meta.app_secret": "",
    "google.client_id": "", "google.client_secret": "",
    "telegram.api_id": "", "telegram.api_hash": "",
    "telegram.agency_bot_token": "",
    "youtube.api_key": "",
    "scrapecreators.api_key": "",
    "cloudflare.account_id": "", "cloudflare.api_token": "",
    "cloudflare.worker_name": "smm-links", "cloudflare.kv_namespace_id": "",
    "r2.account_id": "", "r2.access_key_id": "", "r2.secret_access_key": "", "r2.bucket": "",
    "oauth.callback_url": "",
}

SECRET_KEYS = {
    "meta.app_secret", "google.client_secret", "telegram.api_hash", "telegram.agency_bot_token",
    "youtube.api_key", "scrapecreators.api_key", "cloudflare.api_token",
    "r2.secret_access_key", "r2.access_key_id", "worker.admin_token",
}
SECRET_PREFIXES = ("ai.keys.",)


def is_secret(key: str) -> bool:
    return key in SECRET_KEYS or key.startswith(SECRET_PREFIXES)


def _ck(key, scope, sid):
    return f"setting:{scope}:{sid}:{key}"


def get_setting(key: str, default: Any = None, *, scope: str = "global", scope_id: int = 0) -> Any:
    from .models import SystemSetting
    ck = _ck(key, scope, scope_id)
    hit = cache.get(ck)
    if hit is not None:
        return copy.deepcopy(hit[0])
    row = SystemSetting.objects.filter(key=key, scope=scope, scope_id=scope_id).first()
    if row is None:
        if scope != "global":
            return get_setting(key, default)
        val = DEFAULTS.get(key, default)
    else:
        val = crypto.decrypt_json(row.value_enc) if row.is_secret and row.value_enc else row.value
    cache.set(ck, (copy.deepcopy(val),), 30)
    return val


def set_setting(key: str, value: Any, *, user=None, scope: str = "global", scope_id: int = 0) -> None:
    from .models import SystemSetting
    secret = is_secret(key)
    defaults = {"is_secret": secret, "updated_by": user,
                "value": None if secret else value,
                "value_enc": crypto.encrypt_json(value) if secret else ""}
    SystemSetting.objects.update_or_create(key=key, scope=scope, scope_id=scope_id, defaults=defaults)
    cache.delete(_ck(key, scope, scope_id))
    from .audit import audit
    audit("setting.changed", user=user, target=key, detail={"secret": secret})


def masked(key: str) -> str:
    val = get_setting(key, "")
    if is_secret(key):
        return crypto.mask(str(val)) if val else ""
    return str(val)


def get_secret(key: str) -> str:
    return get_setting(key, "") or ""
