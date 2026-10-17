"""Story yaratish, akkauntlarga navbat bilan taqsimlash, joylash, statistikani yangilash."""
from __future__ import annotations

import random
from datetime import timedelta

from django.utils import timezone

from apps.core.settings_store import get_setting
from apps.jobs.queue import enqueue

from . import tgclient
from .models import Story, StoryAccount, StoryStat, StoryTarget

MAX_ACCOUNTS = 30
CAPTION_FREE, CAPTION_PREMIUM = 200, 2048


def gap_seconds() -> tuple[int, int]:
    lo = int(get_setting("stories.gap_min_sec", 60))
    hi = max(lo, int(get_setting("stories.gap_max_sec", 180)))
    return lo, hi


def plain_len(caption: str) -> int:
    import re
    return len(re.sub(r"<[^>]+>", "", caption or ""))


def kind_of(name: str) -> str:
    return "video" if name.lower().rsplit(".", 1)[-1] in ("mp4", "mov", "m4v", "webm") else "photo"


def schedule(story: Story, accounts, when=None) -> list[StoryTarget]:
    """Har akkaunt uchun natija qatori + navbat vazifasi. Akkauntlar orasida tasodifiy 1–3 daqiqa oraliq (ban'dan himoya)."""
    accounts = list(accounts)[:MAX_ACCOUNTS]
    random.shuffle(accounts)
    start = max(when or timezone.now(), timezone.now())
    lo, hi = gap_seconds()
    t, out = start, []
    for i, acc in enumerate(accounts):
        if i:
            t = t + timedelta(seconds=random.randint(lo, hi))
        tg, _ = StoryTarget.objects.update_or_create(story=story, account=acc, defaults={"status": "pending", "run_at": t, "error": "", "error_code": ""})
        enqueue("story_publish", {"target_id": tg.pk}, queue="publish", run_at=t, dedupe_key=f"story_pub:{tg.pk}", max_attempts=1)
        out.append(tg)
    story.status = "scheduled" if start > timezone.now() + timedelta(seconds=30) else "sending"
    story.scheduled_at = story.scheduled_at or start
    story.save(update_fields=["status", "scheduled_at"])
    return out


def finalize(story: Story) -> str:
    st = list(story.targets.values_list("status", flat=True))
    if story.status == "cancelled":
        return story.status
    if any(s in ("pending", "sending") for s in st):
        new = story.status if story.status == "scheduled" else "sending"
    elif st and all(s == "sent" for s in st):
        new = "done"
    elif any(s == "sent" for s in st):
        new = "partial"
    elif st:
        new = "failed"
    else:
        new = story.status
    if new != story.status:
        story.status = new
        story.save(update_fields=["status"])
    return new


def prepare_media(story: Story) -> str:
    """9:16 ga moslangan fayl yo'li (asl fayl o'zgarmaydi)."""
    path = story.media.path
    if story.fit_mode == "orig":
        return path
    from apps.content.mediafit import MediaFitError, fit_path
    try:
        return fit_path(path, story.kind, "v_9x16", story.fit_mode if story.fit_mode in ("pad", "crop") else "pad")
    except MediaFitError as e:
        raise tgclient.StoryError("media", str(e)) from e


def _spec(story: Story, path: str, acc: StoryAccount) -> dict:
    return {"path": path, "kind": story.kind, "caption": story.caption, "period": story.period, "privacy": story.privacy, "pinned": story.pinned,
            "noforwards": story.noforwards, "link_url": story.link_url, "reaction": story.reaction, "lat": story.geo_lat, "lon": story.geo_lon,
            "account_pk": acc.pk}


def _fail(tg: StoryTarget, err: tgclient.StoryError) -> None:
    tg.status, tg.error_code, tg.error = "error", err.code, err.message_uz[:400]
    tg.save(update_fields=["status", "error_code", "error"])
    if err.code == "auth":
        StoryAccount.objects.filter(pk=tg.account_id).update(status="error", last_error=err.message_uz[:300])


def publish_target(target_id: int) -> str:
    tg = StoryTarget.objects.select_related("story", "account").filter(pk=target_id).first()
    if not tg or tg.status != "pending":
        return "skip"
    story, acc = tg.story, tg.account
    if story.status == "cancelled":
        tg.status, tg.error = "skipped", "Story to'xtatilgan."
        tg.save(update_fields=["status", "error"])
        return "cancelled"
    now = timezone.now()
    if acc.status != "active":
        _fail(tg, tgclient.StoryError("auth" if acc.status == "error" else "other", "akkaunt faol emas"))
        finalize(story)
        return "inactive"
    if acc.cooldown_until and acc.cooldown_until > now:
        tg.run_at = acc.cooldown_until + timedelta(seconds=random.randint(30, 120))
        tg.save(update_fields=["run_at"])
        enqueue("story_publish", {"target_id": tg.pk}, queue="publish", run_at=tg.run_at, max_attempts=1)
        return "cooldown"
    if plain_len(story.caption) > CAPTION_FREE and not acc.is_premium:
        _fail(tg, tgclient.StoryError("premium", "sarlavha 200 belgidan uzun"))
        finalize(story)
        return "premium"
    tg.status = "sending"
    tg.save(update_fields=["status"])
    try:
        path = prepare_media(story)
        res = tgclient.post_story(acc.string_session(), _spec(story, path, acc))
    except tgclient.StoryError as e:
        if e.code == "flood" and 0 < e.wait <= 3600:
            until = now + timedelta(seconds=e.wait + random.randint(60, 300))
            StoryAccount.objects.filter(pk=acc.pk).update(cooldown_until=until)
            tg.status, tg.run_at = "pending", until
            tg.save(update_fields=["status", "run_at"])
            enqueue("story_publish", {"target_id": tg.pk}, queue="publish", run_at=until, max_attempts=1)
            return "flood"
        _fail(tg, e)
        finalize(story)
        return e.code
    tg.status, tg.tg_story_id, tg.sent_at, tg.error, tg.error_code = "sent", res["id"], timezone.now(), "", ""
    tg.save(update_fields=["status", "tg_story_id", "sent_at", "error", "error_code"])
    for off in (1800, 10800, 43200, int(story.period) + 600):
        enqueue("story_stats", {"target_id": tg.pk}, queue="publish", run_at=timezone.now() + timedelta(seconds=off), dedupe_key=f"story_stats:{tg.pk}:{off}", max_attempts=1)
    finalize(story)
    return "sent"


def refresh_stats(target_id: int) -> bool:
    tg = StoryTarget.objects.select_related("account").filter(pk=target_id, status="sent").first()
    if not tg or not tg.tg_story_id or tg.account.status == "error":
        return False
    try:
        s = tgclient.fetch_stats(tg.account.string_session(), tg.tg_story_id, tg.account_id)
    except tgclient.StoryError:
        return False
    tg.views, tg.forwards, tg.reactions, tg.stats_at = s["views"], s["forwards"], s["reactions"], timezone.now()
    tg.save(update_fields=["views", "forwards", "reactions", "stats_at"])
    StoryStat.objects.create(target=tg, views=tg.views, forwards=tg.forwards, reactions=tg.reactions)
    return True


def retry_target(tg: StoryTarget) -> None:
    if tg.status != "error":
        return
    tg.status, tg.error, tg.error_code, tg.run_at = "pending", "", "", timezone.now()
    tg.save(update_fields=["status", "error", "error_code", "run_at"])
    enqueue("story_publish", {"target_id": tg.pk}, queue="publish", max_attempts=1)
    if tg.story.status in ("failed", "partial", "done"):
        tg.story.status = "sending"
        tg.story.save(update_fields=["status"])


def cancel(story: Story) -> int:
    """Hali yuborilmagan (kutilayotgan) akkauntlar uchun to'xtatish. Joylanganlar o'z holicha qoladi (o'chirish yo'q)."""
    n = story.targets.filter(status="pending").update(status="skipped", error="Foydalanuvchi to'xtatdi.")
    story.status = "cancelled" if not story.targets.filter(status="sent").exists() else finalize(story)
    story.save(update_fields=["status"])
    return n


def sync_account(acc: StoryAccount) -> None:
    """Premium/holatni Telegramdan yangilaydi."""
    try:
        info = tgclient.account_info(acc.string_session())
    except tgclient.StoryError as e:
        acc.status, acc.last_error = ("error" if e.code == "auth" else acc.status), e.message_uz[:300]
        acc.save(update_fields=["status", "last_error"])
        return
    acc.tg_user_id, acc.username, acc.is_premium = info["id"], info["username"], info["premium"]
    if acc.status == "error":
        acc.status = "active"
    acc.last_error = ""
    acc.save(update_fields=["tg_user_id", "username", "is_premium", "status", "last_error"])
