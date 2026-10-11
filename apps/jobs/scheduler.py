"""Jadval: har 10 soniyada chaqiriladi, kerakli vazifalarni dedupe kaliti bilan navbatga qo'yadi.
Jadval holati DB dagi jobs jadvalida (dedupe_key) saqlanadi — qayta ishga tushganda yo'qolmaydi."""
from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from apps.core.settings_store import get_setting
from apps.core.utils import local

from .queue import enqueue


def _slots(account=None) -> list[str]:
    return (getattr(account, "collect_schedule", None) or get_setting("collect.schedule", [])) or []


def _latest_passed_slot(slots: list[str], now_local: datetime) -> str | None:
    passed = [s for s in sorted(slots) if s <= now_local.strftime("%H:%M")]
    return passed[-1] if passed else None


def tick(now: datetime | None = None) -> dict:
    from apps.connections.models import Competitor, SocialAccount
    from apps.content.models import ContentItem
    now = now or timezone.now()
    nl = local(now)
    out = {"collect": 0, "stories": 0, "tokens": 0, "publish": 0, "competitors": 0}
    if get_setting("collect.enabled", True):
        for acc in SocialAccount.objects.filter(status__in=["active", "token_expiring"], archived_at__isnull=True):
            if not acc.history_imported:
                if enqueue("historical_import", {"connection_id": acc.pk, "days": int(get_setting("collect.history_days", 365))},
                           dedupe_key=f"hist:{acc.pk}", business_id=acc.business_id, queue="collect", dedupe_any_status=True):
                    out["collect"] += 1
                continue
            slot = _latest_passed_slot(_slots(acc), nl)
            if slot and enqueue("collect_account", {"connection_id": acc.pk, "mode": "regular"},
                                dedupe_key=f"collect:{acc.pk}:{nl.date()}:{slot}", business_id=acc.business_id,
                                dedupe_any_status=True):
                out["collect"] += 1
            if acc.platform == "instagram":
                mins = int(get_setting("collect.story_snapshot_minutes", 60))
                bucket = int(now.timestamp() // (mins * 60))
                if enqueue("story_snapshot", {"connection_id": acc.pk}, dedupe_key=f"story:{acc.pk}:{bucket}",
                           business_id=acc.business_id, dedupe_any_status=True):
                    out["stories"] += 1
                from apps.metrics.models import Story
                after = float(get_setting("collect.story_deep_after_hours", 20))
                if Story.objects.filter(account=acc, finalized=False, published_at__lte=now - timedelta(hours=after), expires_at__gt=now - timedelta(minutes=30)).exists():
                    dm = max(5, int(get_setting("collect.story_deep_minutes", 20)))
                    if enqueue("story_deep", {"connection_id": acc.pk}, dedupe_key=f"storyd:{acc.pk}:{int(now.timestamp() // (dm * 60))}",
                               business_id=acc.business_id, dedupe_any_status=True):
                        out["stories"] += 1
            if acc.platform == "youtube":   # access token 1 soat yashaydi, refresh token avtomatik ishlatiladi — «tugayapti» holati kerak emas
                if acc.status == "token_expiring" or acc.token_expires_at:
                    acc.status = "active" if acc.status == "token_expiring" else acc.status
                    acc.token_expires_at = None
                    acc.save(update_fields=["status", "token_expires_at"])
            elif acc.token_expires_at and acc.token_expires_at < now + timedelta(days=7):
                if acc.status == "active":
                    acc.status = "token_expiring"
                    acc.save(update_fields=["status"])
                if acc.platform == "instagram" and enqueue("token_refresh", {"connection_id": acc.pk},
                                                           dedupe_key=f"tok:{acc.pk}:{nl.date()}", business_id=acc.business_id,
                                                           dedupe_any_status=True):
                    out["tokens"] += 1
        # raqobatchilar: engil — har kuni (birinchi slotdan keyin), og'ir — haftada bir
        first = (sorted(get_setting("collect.schedule", [])) or ["08:00"])[0]
        if nl.strftime("%H:%M") >= first:
            light_per_day = int(get_setting("competitors.light_per_day", 3))
            slots_l = sorted(get_setting("collect.schedule", []))[:light_per_day] or [first]
            slot = _latest_passed_slot(slots_l, nl)
            for c in Competitor.objects.filter(active=True):
                if slot and enqueue("collect_competitor", {"competitor_id": c.pk, "depth": "light"},
                                    dedupe_key=f"comp-l:{c.pk}:{nl.date()}:{slot}", business_id=c.business_id,
                                    dedupe_any_status=True):
                    out["competitors"] += 1
                week = f"{nl.isocalendar().year}-{nl.isocalendar().week}"
                if enqueue("collect_competitor", {"competitor_id": c.pk, "depth": "full"},
                           dedupe_key=f"comp-f:{c.pk}:{week}", business_id=c.business_id, dedupe_any_status=True):
                    out["competitors"] += 1
    # nashr: 1 daqiqa ichida vaqti keladigan tasdiqlangan elementlar
    for item in ContentItem.objects.filter(status="scheduled", scheduled_at__lte=now + timedelta(minutes=1)):
        for t in item.targets.filter(status__in=["pending", "failed_retry"]):
            if enqueue("publish_item", {"content_item_id": item.pk, "target_id": t.pk}, queue="publish", priority=1,
                       dedupe_key=f"pub:{item.pk}:{t.pk}", business_id=item.business_id):
                out["publish"] += 1
    # tizim ishlari
    hour_key = nl.strftime("%Y%m%d%H")
    enqueue("r2_cleanup", {}, dedupe_key=f"r2c:{hour_key}", dedupe_any_status=True)
    enqueue("trash_purge", {}, dedupe_key=f"tp:{nl.date()}", dedupe_any_status=True)
    if nl.hour >= 8:
        enqueue("activity_digest", {}, dedupe_key=f"ad:{nl.date()}", dedupe_any_status=True)
    enqueue("health_probe", {}, dedupe_key=f"hp:{int(now.timestamp() // 300)}", dedupe_any_status=True)
    if get_setting("worker.cloudflare_url", ""):
        enqueue("link_sync", {}, dedupe_key=f"ls:{int(now.timestamp() // 900)}", dedupe_any_status=True)
    if nl.hour >= 3 and nl.minute >= 30 or nl.hour > 3:
        enqueue("backup_db", {}, dedupe_key=f"bk:{nl.date()}", dedupe_any_status=True)
    # g'oyalar banki: har kuni 07:00 dan keyin har bir biznes uchun kamida 1 ta g'oya (tahlildan)
    if nl.hour >= 7 and get_setting("ideas.daily_enabled", True):
        from apps.businesses.models import Business
        for b in Business.objects.all():
            enqueue("ideas_daily", {"business_id": b.pk}, dedupe_key=f"idea:{b.pk}:{nl.date()}", business_id=b.pk, dedupe_any_status=True)
    # kunlik statistika: bugunni har 30 daqiqada yangilab turadi; kechasi (00:05 dan keyin) kechagi kunni yakunlaydi
    enqueue("daily_rollup", {}, dedupe_key=f"dr:{int(now.timestamp() // 1800)}", dedupe_any_status=True)
    if nl.hour > 0 or nl.minute >= 5:
        yd = nl.date() - timedelta(days=1)
        enqueue("daily_rollup_day", {"day": yd.isoformat()}, dedupe_key=f"drd:{yd}", dedupe_any_status=True)
    enqueue("report_schedules", {}, dedupe_key=f"rs:{int(now.timestamp() // 600)}", dedupe_any_status=True)
    enqueue("goals_snapshot", {}, dedupe_key=f"gs:{int(now.timestamp() // 21600)}", dedupe_any_status=True)
    if nl.hour >= 6:
        enqueue("facts_refresh", {}, dedupe_key=f"fr:{nl.date()}", dedupe_any_status=True)
    enqueue("smart_alerts", {}, dedupe_key=f"sa:{int(now.timestamp() // 1800)}", dedupe_any_status=True)
    enqueue("anomaly_scan", {}, dedupe_key=f"an:{nl.date()}:{nl.hour // 6}", dedupe_any_status=True)
    return out
