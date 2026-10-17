"""Story yaratish, akkauntlarga navbat bilan taqsimlash, joylash, statistikani yangilash."""
from __future__ import annotations

import random
from datetime import timedelta

from django.conf import settings
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
        if new in ("done", "partial", "failed"):
            _notify_result(story, new)
    return new


def _notify_result(story: Story, status: str) -> None:
    try:
        from apps.core.notify import notify
        sent = story.targets.filter(status="sent").count()
        total = story.targets.count()
        title = {"done": "Story hammasiga joylandi", "partial": "Story qisman joylandi", "failed": "Story joylanmadi"}[status]
        notify("stories.result", f"{title}: {story.title[:60]}", f"{sent} / {total} akkauntga joylandi.", severity="info" if status == "done" else "warn",
               link=f"/stories/{story.pk}/", dedupe_key=f"story:{story.pk}:{status}", dedupe_minutes=60 * 24)
    except Exception:  # noqa: BLE001
        pass


def prepare_media(story: Story) -> str:
    """9:16 ga moslangan fayl yo'li (asl fayl o'zgarmaydi)."""
    if story.music_video:
        return story.music_video.path   # musiqa bilan tayyor 9:16 mp4
    path = story.media.path
    if story.fit_mode == "orig":
        return path
    from apps.content.mediafit import MediaFitError, fit_path
    try:
        return fit_path(path, story.kind, "v_9x16", story.fit_mode if story.fit_mode in ("pad", "crop") else "pad")
    except MediaFitError as e:
        raise tgclient.StoryError("media", str(e)) from e


def _spec(story: Story, path: str, acc: StoryAccount) -> dict:
    return {"path": path, "kind": "video" if story.music_video else story.kind, "caption": story.caption, "period": story.period, "privacy": story.privacy, "pinned": story.pinned,
            "noforwards": story.noforwards, "link_url": story.link_url, "reaction": story.reaction, "lat": story.geo_lat, "lon": story.geo_lon,
            "account_pk": acc.pk}


def _fail(tg: StoryTarget, err: tgclient.StoryError) -> None:
    tg.status, tg.error_code, tg.error = "error", err.code, err.message_uz[:400]
    tg.save(update_fields=["status", "error_code", "error"])
    if err.code == "auth":
        StoryAccount.objects.filter(pk=tg.account_id).update(status="error", last_error=err.message_uz[:300])
        _notify_account(tg.account_id, "Akkauntni qayta ulash kerak")
    elif err.code == "limit":
        StoryAccount.objects.filter(pk=tg.account_id).update(can_post=False, remains=0, checked_at=timezone.now())


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
    if acc.status != "active":   # (muvaffaqiyatli joylashda can_post yangilanadi)
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
    StoryAccount.objects.filter(pk=acc.pk).update(can_post=True, checked_at=timezone.now())
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


def attach_music(story: Story, track: dict, start: int, length: int) -> None:
    """Tanlangan Jamendo qo'shig'ini story mediasi bilan birlashtirib, music_video ga saqlaydi. MusicError ko'taradi."""
    import os
    import tempfile

    from django.core.files import File as DjFile

    from apps.content.mediafit import MediaFitError, fit_path

    from . import music
    length = music.clamp_len(length)
    src = story.media.path
    try:
        fitted = fit_path(src, story.kind, "v_9x16", story.fit_mode if story.fit_mode in ("pad", "crop") else "pad") if story.fit_mode != "orig" else src
    except MediaFitError as e:
        raise music.MusicError(str(e)) from e
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "story_music.mp4")
        music.build_video(fitted, story.kind, track["audio"], start, length, out)
        with open(out, "rb") as fh:
            story.music_video.save("story_music.mp4", DjFile(fh), save=False)
    story.music_track, story.music_title, story.music_artist = track["id"][:40], track["name"][:200], track["artist"][:200]
    story.music_license, story.music_start, story.music_len = track.get("license", "")[:300], max(0, int(start or 0)), length


# ───────────── akkaunt holati (yuklash imkoniyati) ─────────────
PROBLEM = ("cooldown", "limit")
LIMIT_RECHECK = timedelta(hours=6)


def _hm(dt) -> str:
    from apps.core.utils import local
    return local(dt).strftime("%H:%M") if dt else ""


def account_state(acc: StoryAccount, at=None, sent24: int | None = None) -> dict:
    """Bazadagi ma'lumotlardan akkaunt holati (tarmoqsiz). at — rejalashtirilgan vaqt (None = hozir)."""
    now = timezone.now()
    at = at or now
    if sent24 is None:
        sent24 = acc.targets.filter(status="sent", sent_at__gte=now - timedelta(hours=24)).count()
    base = {"id": acc.pk, "name": acc.name, "sent24": sent24, "remains": acc.remains, "ready_at": None, "checked": _hm(acc.checked_at)}
    if acc.status == "error":
        return {**base, "code": "auth", "level": "bad", "label": "Qayta ulash kerak", "problem": False}
    if acc.status == "paused":
        return {**base, "code": "paused", "level": "warn", "label": "To'xtatilgan", "problem": False}
    if acc.cooldown_until and acc.cooldown_until > at:
        return {**base, "code": "cooldown", "level": "warn", "label": f"FloodWait: {_hm(acc.cooldown_until)} gacha", "ready_at": acc.cooldown_until, "problem": True}
    if acc.can_post is False and acc.checked_at and now - acc.checked_at < LIMIT_RECHECK and at < now + LIMIT_RECHECK:
        return {**base, "code": "limit", "level": "warn", "label": f"Limit tugagan (tekshiruv {_hm(acc.checked_at)})", "problem": True}
    extra = f" · ~{acc.remains} ta qoldi" if acc.remains is not None and acc.can_post else ""
    return {**base, "code": "ready", "level": "ok", "label": "Tayyor" + extra, "problem": False}


def states(accounts, at=None) -> list[dict]:
    from django.db.models import Count
    now = timezone.now()
    ids = [a.pk for a in accounts]
    cnt = dict(StoryTarget.objects.filter(account_id__in=ids, status="sent", sent_at__gte=now - timedelta(hours=24)).values_list("account_id").annotate(n=Count("id")))
    return [account_state(a, at, cnt.get(a.pk, 0)) for a in accounts]


def check_account(acc: StoryAccount) -> dict:
    """Telegramdan hozirgi imkoniyatni so'rab, saqlaydi. Natija: account_state."""
    try:
        r = tgclient.can_send(acc.string_session(), acc.pk)
    except tgclient.StoryError as e:
        if e.code == "auth":
            acc.status, acc.last_error = "error", e.message_uz[:300]
            acc.save(update_fields=["status", "last_error"])
            _notify_account(acc.pk, "Akkauntni qayta ulash kerak")
        elif e.code == "flood" and e.wait:
            acc.cooldown_until = timezone.now() + timedelta(seconds=min(e.wait, 86400))
            acc.save(update_fields=["cooldown_until"])
        return account_state(acc)
    acc.can_post, acc.remains, acc.checked_at = r["ok"], r["remains"], timezone.now()
    acc.save(update_fields=["can_post", "remains", "checked_at"])
    return account_state(acc)


def check_all(ids=None) -> int:
    import time
    qs = StoryAccount.objects.filter(status="active")
    if ids:
        qs = qs.filter(pk__in=ids)
    n = 0
    for acc in qs:
        check_account(acc)
        n += 1
        if not getattr(settings, "USE_FAKES", False):
            time.sleep(random.uniform(1.0, 2.5))
    return n


def _notify_account(account_pk: int, title: str) -> None:
    try:
        from apps.core.notify import notify
        acc = StoryAccount.objects.filter(pk=account_pk).first()
        if acc:
            notify("stories.account", f"{title}: {acc.name}", acc.last_error[:200], severity="warn", link="/stories/akkauntlar/",
                   dedupe_key=f"storyacc:{account_pk}:{title[:10]}", dedupe_minutes=720)
    except Exception:  # noqa: BLE001
        pass


# ───────────── oldindan tekshiruv va vaqt tavsiyasi ─────────────
SLOT_HOURS = (9, 12, 18, 21)


def preflight(accounts, at=None) -> dict:
    """Tanlangan akkauntlar va vaqt uchun: holatlar, to'qnashuvlar, tugash vaqti, tavsiya etilgan vaqtlar."""
    from apps.core.utils import local, tz
    now = timezone.now()
    accounts = list(accounts)[:MAX_ACCOUNTS]
    st = states(accounts, at)
    start = max(at or now, now)
    lo, hi = gap_seconds()
    n = len(accounts)
    finish = start + timedelta(seconds=((lo + hi) / 2) * max(n - 1, 0))
    conflicts = []
    if accounts:
        near = StoryTarget.objects.filter(account__in=accounts, status="pending", run_at__gte=start - timedelta(minutes=15), run_at__lte=finish + timedelta(minutes=15)).select_related("account", "story")
        conflicts = [{"account": t.account.name, "story": t.story.title[:40], "at": _hm(t.run_at)} for t in near[:10]]
    ready_at = max([s["ready_at"] for s in st if s["ready_at"]] or [None], key=lambda x: x or now) if any(s["ready_at"] for s in st) else None
    earliest = max(now + timedelta(minutes=2), (ready_at or now) + timedelta(minutes=2))
    sug = []
    if ready_at and ready_at > start:
        sug.append({"label": f"Eng erta: {_hm(earliest)} (barcha akkaunt tayyor)", "value": local(earliest).strftime("%Y-%m-%dT%H:%M")})
    day = local(earliest).date()
    for d in range(0, 3):
        for h in SLOT_HOURS:
            from datetime import datetime as _dt
            cand = _dt.combine(day + timedelta(days=d), _dt.min.time()).replace(hour=h, tzinfo=tz())
            if cand > earliest + timedelta(minutes=5) and len(sug) < 4:
                busy = StoryTarget.objects.filter(status="pending", run_at__gte=cand - timedelta(minutes=20), run_at__lte=cand + timedelta(minutes=20)).exists()
                sug.append({"label": f"{local(cand):%d.%m %H:%M}" + (" (band)" if busy else ""), "value": f"{local(cand):%Y-%m-%dT%H:%M}"})
    return {"accounts": [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in s.items()} for s in st],
            "problems": sum(1 for s in st if s["problem"]), "ready": sum(1 for s in st if not s["problem"]), "conflicts": conflicts,
            "finish": _hm(finish), "start": _hm(start), "suggestions": sug}


# ───────────── orqa fonda tayyorlash (musiqali video) ─────────────
def prepare_story(story_id: int, account_ids: list[int], when_iso: str | None) -> str:
    from datetime import datetime

    from . import music
    story = Story.objects.filter(pk=story_id).first()
    if not story or story.status != "preparing":
        return "skip"

    def fail(msg: str) -> str:
        story.status, story.prepare_error = "failed", msg[:300]
        story.save(update_fields=["status", "prepare_error"])
        try:
            from apps.core.notify import notify
            notify("stories.result", f"Story tayyorlanmadi: {story.title[:60]}", msg[:200], severity="warn", link=f"/stories/{story.pk}/", dedupe_key=f"storyprep:{story.pk}")
        except Exception:  # noqa: BLE001
            pass
        return "failed"
    try:
        track = {"id": story.music_track, "name": story.music_title, "artist": story.music_artist, "audio": story.music_src, "license": story.music_license}
        if story.music_src and not story.music_video:
            attach_music(story, track, story.music_start, story.music_len)
            story.save()
    except music.MusicError as e:
        return fail(e.message_uz)
    except Exception as e:  # noqa: BLE001
        return fail(f"Tayyorlashda kutilmagan xato: {e}")
    story.refresh_from_db()
    if story.status != "preparing":     # foydalanuvchi to'xtatgan
        return "cancelled"
    accs = list(StoryAccount.objects.filter(pk__in=account_ids, status="active"))
    if not accs:
        return fail("Tanlangan akkauntlar faol emas.")
    when = datetime.fromisoformat(when_iso) if when_iso else None
    schedule(story, accs, when)
    return "scheduled"


def watchdog() -> int:
    """Qotib qolgan «Tayyorlanmoqda» storylarni «Xato»ga o'tkazadi (20 daqiqadan ortiq va ishlayotgan vazifa yo'q)."""
    from apps.jobs.models import Job
    n = 0
    for s in Story.objects.filter(status="preparing", created_at__lt=timezone.now() - timedelta(minutes=20)):
        if Job.objects.filter(type="story_prepare", status__in=["pending", "running"], dedupe_key=f"story_prep:{s.pk}").exists():
            continue
        s.status, s.prepare_error = "failed", "Tayyorlash qotib qoldi. Qaytadan yarating."
        s.save(update_fields=["status", "prepare_error"])
        n += 1
    return n
