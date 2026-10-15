"""Nashr xizmati (CONTRACTS §9) va kontent yordamchilari."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.connections.base import (AuthError, Capability, ContentRejectedError, MediaType, PlatformError, PublishRequest,
                                   TransientError)
from apps.connections.registry import get_connector
from apps.core.audit import audit
from apps.core.notify import notify
from apps.core.settings_store import get_setting
from apps.jobs.queue import enqueue

from . import mediafit, temphost
from .models import ContentItem, PublishAttempt, RuleCheckResult
from .rules import run_rules
from .state import transition

log = logging.getLogger(__name__)


class NotReady(Exception):
    code = "rule_blocked"

    def __init__(self, msg, problems=None):
        super().__init__(msg)
        self.problems = problems or []


def check_item(item: ContentItem) -> dict:
    """Har bir maqsad (tarmoq) uchun qoidalarni ishga tushiradi va natijani saqlaydi."""
    worst, report = "pass", {}
    order = {"pass": 0, "warn": 1, "block": 2}
    targets = list(item.targets.select_related("account"))
    plats = [t.account.platform for t in targets] or ["telegram"]
    for pl in dict.fromkeys(plats):
        out = run_rules(item, pl)
        probs = [p.__dict__ for p in out.problems]
        RuleCheckResult.objects.create(item=item, platform=pl, status=out.status, problems=probs)
        report[pl] = {"status": out.status, "problems": probs}
        if order[out.status] > order[worst]:
            worst = out.status
    item.rule_status = worst
    item.save(update_fields=["rule_status"])
    return {"status": worst, "platforms": report}


def ensure_ready_to_schedule(item: ContentItem) -> None:
    if not item.targets.exists():
        raise NotReady("Hech bir tarmoq tanlanmagan.")
    res = check_item(item)
    if res["status"] == "block" and not item.rule_override_by_id:
        raise NotReady("Qoida bo'yicha nashr to'xtatildi.", res["platforms"])


def override_warnings(item: ContentItem, user, reason: str) -> None:
    from apps.accounts.services import perms
    if not perms.can(user, "publish.publish", item.business):
        raise PermissionError("Ogohlantirishni chetlab o'tishga ruxsat yo'q.")
    reason = (reason or "").strip() or "Muallif qoida natijasini ko'rib, nashrga ruxsat berdi."
    item.rule_override_by, item.rule_override_reason = user, reason[:300]
    item.save(update_fields=["rule_override_by", "rule_override_reason"])
    audit("content.rule_override", user=user, business_id=item.business_id, target=f"item:{item.pk}", detail={"reason": reason})


def _media_type(item: ContentItem) -> MediaType:
    return MediaType(item.media_type)


def _idem_key(item, target) -> str:
    return f"{item.pk}:{target.pk}:{item.content_hash()[:16]}"


def _finalize_item(item: ContentItem) -> None:
    sts = set(item.targets.values_list("status", flat=True))
    if sts and sts <= {"published"}:
        item.status = "published"
    elif sts & {"pending", "publishing", "failed_retry"}:
        item.status = "publishing" if "publishing" in sts else item.status
    elif "failed" in sts or "blocked" in sts:
        item.status = "failed"
    item.save(update_fields=["status"])
    if item.status == "published":
        cleanup_temp_for(item)


def cleanup_temp_for(item: ContentItem) -> int:
    n = 0
    if temphost.retention_manual() and not settings.USE_FAKES:
        return 0   # Cloudflare fayllari faqat qo'lda o'chiriladi
    for o in item.temp_objects.filter(status="uploaded"):
        temphost.delete_object(o, fake=settings.USE_FAKES)
        n += 1
    return n


def _prepare_request(item, target, conn) -> PublishRequest:
    assets = [(a.file.path, a.kind) for a in item.assets.order_by("position", "id") if a.file and a.kind in ("image", "video")]
    opts0 = item.options or {}
    key, mode, plat = opts0.get("media_size") or "orig", opts0.get("fit_mode") or "pad", target.account.platform
    try:
        paths = []
        for pth, kind in assets:
            paths.append(mediafit.fit_for_platform(pth, kind, key, mode, opts0.get("crop"), plat))
    except mediafit.MediaFitError as e:
        raise ContentRejectedError(str(e), user_message_uz=str(e))
    thumb = next((a.file.path for a in item.assets.filter(kind="thumbnail") if a.file), None)
    opts = dict(item.options or {})
    if thumb:
        opts["thumbnail"] = thumb
    return PublishRequest(idempotency_key=_idem_key(item, target), media_type=_media_type(item), text=item.text,
                          media_paths=paths, scheduled_at=item.scheduled_at, options=opts)


def _needs_url(req: PublishRequest, platform: str) -> bool:
    if platform != "instagram":
        return False
    vids = req.media_type in (MediaType.REEL, MediaType.VIDEO, MediaType.SHORT)
    return not vids  # rasm/karusel/story: ochiq URL kerak (video resumable)


def _host_all(item, req: PublishRequest) -> PublishRequest:
    from dataclasses import replace
    urls = []
    by_path = {a.file.path: a for a in item.assets.all() if a.file}
    for p in req.media_paths:
        a = by_path.get(p)
        o = (a.cloud if a and a.cloud_id and a.cloud.status == "uploaded" else None) or (a.cloud_objects.filter(status="uploaded").first() if a else None)   # allaqachon yuklangan bo'lsa qayta yuklanmaydi
        if o is None:
            pend = a.cloud_objects.filter(status__in=["pending", "failed"]).first() if a else None
            o = temphost.host_file(p, item, fake=settings.USE_FAKES, asset=a, obj=pend)
        urls.append(temphost.fresh_url(o) if o.backend == "r2" else o.public_url)
    return replace(req, media_public_urls=urls)


def _already_published(conn, item, target):
    """Noaniq xatodan keyin qayta urinishda takroriy nashrni oldini olish."""
    if Capability.POSTS not in conn.capabilities or settings.USE_FAKES:
        return None
    try:
        since = (item.scheduled_at or timezone.now()) - timedelta(minutes=15)
        head = (item.text or "")[:60].strip()
        for p in conn.fetch_posts(since).items:
            if head and (p.text or "").strip().startswith(head):
                return p
    except PlatformError:
        return None
    return None


def publish_target(item_id: int, target_id: int) -> dict:
    """Bitta tarmoqqa nashr: qayta tekshiruv -> quruq tekshiruv -> media -> nashr -> natija."""
    item = ContentItem.objects.select_related("business").get(pk=item_id)
    target = item.targets.select_related("account").get(pk=target_id)
    acc = target.account
    now = timezone.now()
    # idempotentlik: muvaffaqiyatli bo'lsa darhol tugaydi
    if target.status == "published":
        return {"skipped": "already_published"}
    key = _idem_key(item, target)
    prev = PublishAttempt.objects.filter(idempotency_key=key).first()
    if prev and prev.status == "success":
        _mark_published(item, target, prev.external_id, target.url, prev.finished_at or now)
        return {"skipped": "attempt_success"}
    if prev and prev.status == "started" and prev.started_at > now - timedelta(minutes=15):
        raise TransientError("Nashr jarayonda (boshqa oqim).")
    # 2-bosqich: qayta tekshiruvlar
    reasons = []
    if item.status not in ("scheduled", "publishing", "failed"):
        reasons.append(f"holat: {item.status}")
    if not (item.business.autopublish_enabled and acc.autopublish_enabled):
        target.status, target.blocked_by_kill_switch, target.error = "blocked", True, "Avtonashr to'xtatilgan (kill switch)"
        target.save(update_fields=["status", "blocked_by_kill_switch", "error"])
        return {"blocked": "kill_switch"}
    if acc.status not in ("active", "token_expiring"):
        reasons.append(f"ulanish holati: {acc.status}")
    if reasons:
        _fail(item, target, "To'sildi: " + "; ".join(reasons), retryable=False, status="blocked")
        return {"blocked": reasons}
    chk = check_item(item)
    if chk["status"] == "block" and not item.rule_override_by_id:
        _fail(item, target, "Qoidalar nashrni to'xtatdi", retryable=False, status="blocked")
        return {"blocked": "rules"}
    late = int(get_setting("publish.late_policy_min", 30))
    if item.scheduled_at and now > item.scheduled_at + timedelta(minutes=late):
        _fail(item, target, f"Nashr vaqti o'tib ketdi (>{late} daqiqa)", retryable=False)
        notify("publish.missed_window", f"Nashr vaqti o'tib ketdi: {item.title}", business_id=item.business_id,
               severity="warn", link=f"/kalendar/{item.pk}/")
        return {"failed": "missed_window"}
    if item.status == "scheduled":
        transition(item, "publishing", None)
    target.status = "publishing"
    target.save(update_fields=["status"])
    attempt = prev or PublishAttempt(target=target, idempotency_key=key, number=target.attempts.count() + 1)
    attempt.status, attempt.started_at = "started", now
    attempt.save()
    conn = get_connector(acc)
    try:
        req = _prepare_request(item, target, conn)
        dry = conn.dry_run(req)
        if not dry.ok:
            raise ContentRejectedError("; ".join(p.message_uz for p in dry.problems),
                                       user_message_uz="; ".join(p.message_uz for p in dry.problems))
        if attempt.number > 1:
            found = _already_published(conn, item, target)
            if found:
                res_id, res_url, res_at = found.external_id, found.url, found.published_at
                return _success(item, target, attempt, res_id, res_url, res_at)
        if _needs_url(req, acc.platform):
            req = _host_all(item, req)
        try:
            result = conn.publish(req)
        except (TransientError, PlatformError) as e:
            # video: resumable ishlamasa -> ochiq URL zaxira yo'li
            if (acc.platform == "instagram" and req.media_paths and not req.media_public_urls and not e.__class__.__name__.startswith("Token")
                    and get_setting("publish.use_r2", "auto") != "never" and not isinstance(e, (AuthError, ContentRejectedError))):
                from dataclasses import replace
                req2 = _host_all(item, replace(req, options={**req.options, "upload_mode": "url"}))
                result = conn.publish(req2)
            else:
                raise
        return _success(item, target, attempt, result.external_id, result.url, result.published_at, result.raw)
    except temphost.WaitingForSpace:
        attempt.status = "failed"
        attempt.error = "R2 joyi yetmaydi"
        attempt.save()
        target.status = "pending"
        target.save(update_fields=["status"])
        raise TransientError("R2 joyi yetmaydi; navbatda kutadi.")
    except PlatformError as e:
        attempt.status, attempt.error, attempt.retryable = "failed", f"{type(e).__name__}: {e}"[:2000], bool(e.retryable)
        attempt.finished_at = timezone.now()
        attempt.save()
        max_att = int(get_setting("publish.max_attempts", 3))
        if e.retryable and attempt.number < max_att:
            target.status = "failed_retry"
            target.error = e.user_message_uz
            target.save(update_fields=["status", "error"])
            raise
        _fail(item, target, e.user_message_uz or str(e), retryable=False)
        return {"failed": str(e)}


def _success(item, target, attempt, ext_id, url, when, raw=None):
    attempt.status, attempt.external_id, attempt.finished_at, attempt.error = "success", ext_id, timezone.now(), ""
    attempt.save()
    _mark_published(item, target, ext_id, url, when, raw)
    return {"published": ext_id, "url": url}


def _mark_published(item, target, ext_id, url, when, raw=None):
    target.status, target.external_id, target.url, target.published_at, target.error = "published", ext_id, url or "", when, ""
    if raw and raw.get("audit_restricted"):
        target.error = "YouTube: video yopiq (private) holatda qoldi — API auditi talab qilinadi."
    target.save()
    _finalize_item(item)
    from apps.metrics.models import Post
    acc = target.account
    post, _ = Post.objects.get_or_create(platform=acc.platform, external_id=ext_id, defaults=dict(
        business=item.business, account=acc, media_type=item.media_type, text=item.text, url=url or "",
        published_at=when, hashtags=[w for w in (item.text or "").split() if w.startswith("#")], content_item=item))
    for win, hours in (("1h", 1), ("6h", 6), ("24h", 24), ("72h", 72)):
        enqueue("collect_post_metrics", {"connection_id": acc.pk, "post_ids": [ext_id], "window": win}, queue="collect",
                run_at=when + timedelta(hours=hours), dedupe_key=f"pm:{post.pk}:{win}", business_id=item.business_id, dedupe_any_status=True)
    enqueue("client_publish_notice", {"target_id": target.pk}, queue="system", run_at=timezone.now() + timedelta(seconds=20),
            dedupe_key=f"cn:{target.pk}", business_id=item.business_id, dedupe_any_status=True)
    for win, hours in (("24h", 24), ("7d", 24 * 7)):
        enqueue("post_summary", {"post_id": post.pk, "window": win}, queue="ai", run_at=when + timedelta(hours=hours, minutes=20),
                dedupe_key=f"ps:{post.pk}:{win}", business_id=item.business_id, dedupe_any_status=True)
    notify("publish.success", f"Nashr qilindi: {item.title}", f"{acc.name}", business_id=item.business_id, link=url or "")
    audit("publish.success", business_id=item.business_id, target=f"item:{item.pk}", detail={"account": acc.pk, "external_id": ext_id})


def _fail(item, target, msg, *, retryable, status="failed"):
    target.status, target.error = status, msg[:400]
    target.save(update_fields=["status", "error"])
    _finalize_item(item)
    if item.status in ("scheduled", "publishing"):
        item.status = "failed"
        item.save(update_fields=["status"])
    notify("publish.failed", f"Nashr xatosi: {item.title}", f"{target.account.name}: {msg}", business_id=item.business_id,
           severity="critical", link=f"/kalendar/{item.pk}/", dedupe_key=f"pubfail:{item.pk}:{target.pk}")
    audit("publish.failed", business_id=item.business_id, target=f"item:{item.pk}", detail={"error": msg})


@transaction.atomic
def retry_failed(item: ContentItem, user) -> int:
    n = item.targets.filter(status__in=["failed", "blocked"]).update(status="pending", error="", blocked_by_kill_switch=False)
    if n:
        if item.status == "failed":
            transition(item, "scheduled", user)
        if item.scheduled_at and item.scheduled_at < timezone.now():
            item.scheduled_at = timezone.now() + timedelta(minutes=1)
            item.save(update_fields=["scheduled_at"])
    return n
