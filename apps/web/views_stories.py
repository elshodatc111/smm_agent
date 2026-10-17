"""Telegram Stories bo'limi: akkauntlar (30 tagacha), story yuklash, alohida kalendar, natija va statistika. Biznesga bog'liq emas."""
from __future__ import annotations

import calendar as pycal
import mimetypes
from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.connections.base import PlatformError
from apps.core import crypto
from apps.core.audit import audit
from apps.core.utils import fmt_dt, local, tz
from apps.jobs.queue import enqueue
from apps.core.settings_store import get_setting
from apps.stories import music, services, tgclient
from apps.stories.models import PERIODS, PRIVACY, Story, StoryAccount, StoryStat, StoryTarget

EXT_OK = ("jpg", "jpeg", "png", "webp", "mp4", "mov", "m4v")
MAX_MB = 200
REACTIONS = ["", "❤", "🔥", "👍", "🎉", "😍", "👏", "😮"]
BADGE = {"draft": "", "preparing": "blue", "scheduled": "blue", "sending": "blue", "done": "ok", "partial": "warn", "failed": "bad", "cancelled": "",
         "pending": "", "sent": "ok", "error": "bad", "skipped": ""}
ERR_UZ = {"premium": "Premium kerak", "limit": "Limit", "flood": "FloodWait", "media": "Fayl xatosi", "auth": "Qayta ulash kerak", "other": "Xato"}


def _tabs(active):
    return [("stories_home", "Bosh sahifa"), ("stories_calendar", "Kalendar"), ("stories_new", "Yangi story"), ("stories_accounts", "Akkauntlar"), ("stories_stats", "Statistika")], active


def _ctx(request, tab, **kw):
    tabs, _ = _tabs(tab)
    return {"tabs": tabs, "tab": tab, **kw}


def _story_row(s: Story):
    t = list(s.targets.all())
    sent = sum(1 for x in t if x.status == "sent")
    errs = sum(1 for x in t if x.status == "error")
    views = sum(x.views for x in t)
    return {"s": s, "total": len(t), "sent": sent, "errs": errs, "views": views, "badge": BADGE.get(s.status, ""), "when": fmt_dt(s.scheduled_at or s.created_at)}


# ───────────────────────── bosh sahifa ─────────────────────────
@login_required
@require_permission("stories.view")
def stories_home(request):
    now = timezone.now()
    accs = StoryAccount.objects.all()
    week = now - timedelta(days=7)
    agg = StoryTarget.objects.filter(status="sent", sent_at__gte=week).aggregate(n=Count("id"), v=Sum("views"))
    cards = [("Akkauntlar", f"{accs.count()} / {services.MAX_ACCOUNTS}"), ("Faol", accs.filter(status="active").count()),
             ("Premium", accs.filter(is_premium=True).count()), ("Rejalashtirilgan", Story.objects.filter(status="scheduled").count()),
             ("7 kunda joylangan", agg["n"] or 0), ("7 kunda ko'rishlar", agg["v"] or 0)]
    recent = [_story_row(s) for s in Story.objects.prefetch_related("targets")[:15]]
    upcoming = [_story_row(s) for s in Story.objects.filter(status="scheduled").prefetch_related("targets").order_by("scheduled_at")[:8]]
    return render(request, "stories_home.html", _ctx(request, "stories_home", title="Telegram Stories", cards=cards, recent=recent, upcoming=upcoming, n_acc=accs.count()))


# ───────────────────────── akkauntlar ─────────────────────────
@login_required
@require_permission("stories.view")
def stories_accounts(request):
    from apps.accounts.services import perms
    return render(request, "stories_accounts.html", _ctx(request, "stories_accounts", title="Stories: akkauntlar", accs=_decorate(list(StoryAccount.objects.all())), tl=request.session.get("stories_tl"),
                                                       can_manage=perms.can(request.user, "stories.configure", None), max_acc=services.MAX_ACCOUNTS))


@login_required
@require_POST
@require_permission("stories.configure")
def stories_account_add(request):
    from apps.connections import telethon_login as tl
    st = request.session.get("stories_tl")
    try:
        if not st:
            phone = request.POST.get("phone", "").strip().replace(" ", "")
            name = (request.POST.get("name") or "Akkaunt").strip()[:80]
            if not phone.startswith("+") or len(phone) < 9:
                raise PermissionError("Telefonni +998901234567 ko'rinishida kiriting.")
            exists = StoryAccount.objects.filter(phone=phone).first()
            if not exists and StoryAccount.objects.count() >= services.MAX_ACCOUNTS:
                raise PermissionError(f"Eng ko'pi bilan {services.MAX_ACCOUNTS} ta akkaunt ulash mumkin.")
            if settings.USE_FAKES:
                StoryAccount.objects.update_or_create(phone=phone, defaults={"name": name, "session_enc": crypto.encrypt("fake"), "status": "active", "connected_at": timezone.now()})
                messages.success(request, "Demo akkaunt qo'shildi.")
                return redirect("stories_accounts")
            r = tl.send_code(phone)
            request.session["stories_tl"] = {**r, "phone": phone, "name": name}
            messages.info(request, "Kod Telegram ilovasiga yuborildi.")
        else:
            r = tl.sign_in(st["phone"], st["session"], st["hash"], code=request.POST.get("code", "").strip(), password=request.POST.get("password", ""))
            if r.get("need_password"):
                request.session["stories_tl"] = {**st, "session": r["session"], "need_password": True}
                messages.info(request, "Ikki bosqichli parol kerak.")
            else:
                acc, _ = StoryAccount.objects.update_or_create(phone=st["phone"], defaults={"name": st["name"], "session_enc": crypto.encrypt(r["session"]), "status": "active",
                                                                                           "last_error": "", "connected_at": timezone.now()})
                services.sync_account(acc)
                request.session.pop("stories_tl", None)
                audit("stories.account_added", user=request.user, target=acc.name)
                messages.success(request, f"Akkaunt ulandi{' (Premium)' if acc.is_premium else ' (Premium emas — ba\'zi imkoniyatlar cheklangan)'}.")
    except PlatformError as e:
        messages.error(request, e.user_message_uz or str(e))
    except PermissionError as e:
        messages.error(request, str(e))
    except Exception as e:  # noqa: BLE001
        request.session.pop("stories_tl", None)
        messages.error(request, f"Kirishda xato: {e}")
    return redirect("stories_accounts")


@login_required
@require_POST
def stories_account_cancel(request):
    request.session.pop("stories_tl", None)
    return redirect("stories_accounts")


@login_required
@require_POST
@require_permission("stories.configure")
def stories_account_action(request, pk):
    a = get_object_or_404(StoryAccount, pk=pk)
    act = request.POST.get("action")
    if act == "toggle":
        a.status = "paused" if a.status == "active" else "active"
        if a.status == "active":
            a.last_error, a.cooldown_until = "", None
        a.save(update_fields=["status", "last_error", "cooldown_until"])
    elif act == "check":
        st = services.check_account(a)
        messages.info(request, f"{a.name}: {st['label']}")
    elif act == "sync":
        services.sync_account(a)
        messages.info(request, "Holat yangilandi.")
    elif act == "rename":
        a.name = (request.POST.get("name") or a.name).strip()[:80]
        a.note = (request.POST.get("note") or "").strip()[:160]
        a.save(update_fields=["name", "note"])
    elif act == "delete":
        audit("stories.account_deleted", user=request.user, target=a.name)
        a.delete()
        messages.success(request, "Akkaunt o'chirildi.")
    return redirect("stories_accounts")


# ───────────────────────── yangi story ─────────────────────────
def _assets():
    """Kontent kalendaridagi mavjud rasm/videolar (nusxa olinadi, asl fayl o'zgarmaydi)."""
    from apps.content.models import ContentAsset
    return list(ContentAsset.objects.filter(kind__in=["image", "video"], item__deleted_at__isnull=True).exclude(file="").select_related("item").order_by("-id")[:60])


def _parse_when(request, errors):
    if request.POST.get("when") != "later":
        return None
    raw = request.POST.get("scheduled_at", "").strip()
    try:
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M").replace(tzinfo=tz())
    except ValueError:
        errors.append("Rejalashtirish vaqtini tanlang.")
        return None
    if dt <= timezone.now():
        errors.append("Rejalashtirilgan vaqt kelajakda bo'lishi kerak.")
    return dt


def _decorate(accs):
    for a, st in zip(accs, services.states(accs)):
        a.state = st
    return accs


def _music_ctx():
    on = music.enabled()
    return {"music_on": on, "music_ready": on and music.configured(), "music_default": music.clamp_len(None)}


def _find_track(track_id: str, q: str = ""):
    """Qo'shiq ro'yxat (kesh)dan olinadi — brauzerdan kelgan audio manzilga ishonilmaydi."""
    try:
        for t in music.top_tracks(q) + (music.top_tracks("") if q else []):
            if t["id"] == str(track_id):
                return t
    except music.MusicError:
        return None
    return None


@login_required
@require_permission("stories.create")
def stories_music_list(request):
    if not music.enabled():
        return JsonResponse({"ok": False, "error": "Musiqa o'chirilgan."})
    try:
        items = music.top_tracks(request.GET.get("q", ""))
    except music.MusicError as e:
        return JsonResponse({"ok": False, "error": e.message_uz})
    return JsonResponse({"ok": True, "items": [{k: t[k] for k in ("id", "name", "artist", "duration", "image", "stream")} | {"audio": t["stream"] or t["audio"]} for t in items]})


@login_required
@require_permission("stories.create")
def stories_preflight(request):
    """Forma uchun: tanlangan akkauntlar va vaqt bo'yicha tayyorlik, to'qnashuv va vaqt tavsiyasi."""
    ids = [int(x) for x in request.GET.getlist("accounts") if x.isdigit()]
    accs = list(StoryAccount.objects.filter(pk__in=ids, status="active"))
    at = None
    raw = request.GET.get("when", "").strip()
    if raw:
        try:
            at = datetime.strptime(raw, "%Y-%m-%dT%H:%M").replace(tzinfo=tz())
        except ValueError:
            at = None
    return JsonResponse(services.preflight(accs, at))


@login_required
@require_POST
@require_permission("stories.create")
def stories_check(request):
    """Akkaunt(lar) imkoniyatini Telegramdan tekshirish: bitta — darhol, hammasi — orqa fonda."""
    pk = request.POST.get("pk")
    if pk and pk.isdigit():
        acc = get_object_or_404(StoryAccount, pk=pk)
        return JsonResponse({"ok": True, "state": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in services.check_account(acc).items()}})
    enqueue("story_check_accounts", {}, queue="publish", max_attempts=1, dedupe_key=f"stchk:manual:{int(timezone.now().timestamp() // 60)}")
    return JsonResponse({"ok": True, "queued": True})


@login_required
@require_permission("stories.view")
def stories_status(request):
    """Bosh sahifadagi jonli panel: worker holati, akkaunt holatlari, jarayondagi storylar."""
    from apps.jobs.models import Job, WorkerHeartbeat
    now = timezone.now()
    beat = WorkerHeartbeat.objects.order_by("-beat_at").values_list("beat_at", flat=True).first()
    alive = bool(beat and beat > now - timedelta(seconds=60))
    live = Story.objects.filter(Q(status__in=["preparing", "sending"]) | Q(status__in=["done", "partial", "failed"], created_at__gte=now - timedelta(hours=6))).prefetch_related("targets__account").order_by("-id")[:8]
    out = []
    for s in live:
        t = list(s.targets.all())
        nxt = min([x.run_at for x in t if x.status == "pending" and x.run_at], default=None)
        out.append({"id": s.pk, "title": s.title, "status": s.status, "label": s.get_status_display(), "badge": BADGE.get(s.status, ""), "total": len(t), "sent": sum(1 for x in t if x.status == "sent"),
                    "errors": sum(1 for x in t if x.status == "error"), "next": local(nxt).strftime("%H:%M") if nxt else "", "prep_error": s.prepare_error, "music": s.music_title,
                    "targets": [{"account": x.account.name, "status": x.status, "label": x.get_status_display(), "badge": BADGE.get(x.status, ""), "at": local(x.run_at).strftime("%H:%M") if x.run_at else "",
                                 "error": ERR_UZ.get(x.error_code, "") if x.status == "error" else ""} for x in t]})
    overdue = Job.objects.filter(type__in=["story_publish", "story_prepare"], status="pending", run_at__lt=now - timedelta(minutes=3)).count()
    accs = list(StoryAccount.objects.all())
    return JsonResponse({"worker": {"alive": alive, "ago": int((now - beat).total_seconds()) if beat else None, "overdue": overdue},
                         "accounts": [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in x.items()} for x in services.states(accs)], "stories": out})


@login_required
@require_permission("stories.create")
def stories_new(request):
    accs = _decorate(list(StoryAccount.objects.all()))
    errors: list[str] = []
    P = request.POST if request.method == "POST" else {}
    if request.method == "POST":
        title = (P.get("title") or "").strip()[:160]
        caption = (P.get("caption") or "").strip()
        period = int(P.get("period") or 86400) if (P.get("period") or "86400").isdigit() else 86400
        privacy = P.get("privacy") if P.get("privacy") in dict(PRIVACY) else "all"
        fit = P.get("fit_mode") if P.get("fit_mode") in ("pad", "crop", "orig") else "pad"
        link = (P.get("link_url") or "").strip()
        reaction = P.get("reaction") if P.get("reaction") in REACTIONS else ""
        lat = lon = None
        if (P.get("geo_lat") or "").strip() or (P.get("geo_lon") or "").strip():
            try:
                lat, lon = float(P["geo_lat"].replace(",", ".")), float(P["geo_lon"].replace(",", "."))
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError
            except (ValueError, KeyError):
                errors.append("Joylashuv: kenglik va uzunlikni to'g'ri raqam bilan kiriting (masalan 41.311, 69.279).")
        if period not in dict(PERIODS):
            period = 86400
        if link and not link.lower().startswith(("http://", "https://")):
            errors.append("Havola http:// yoki https:// bilan boshlanishi kerak.")
        if services.plain_len(caption) > services.CAPTION_PREMIUM:
            errors.append(f"Sarlavha {services.CAPTION_PREMIUM} belgidan oshmasin.")
        ids = request.POST.getlist("accounts")
        chosen = [a for a in accs if str(a.pk) in ids] if P.get("all") != "1" else [a for a in accs if a.status == "active"]
        chosen = [a for a in chosen if a.status == "active"]
        if not chosen:
            errors.append("Kamida bitta faol akkaunt tanlang.")
        up, asset_id = request.FILES.get("media"), P.get("asset")
        src_name = ""
        if up:
            src_name = up.name
            if up.name.lower().rsplit(".", 1)[-1] not in EXT_OK:
                errors.append("Fayl turi: jpg, png, webp, mp4 yoki mov bo'lishi kerak.")
            if up.size > MAX_MB * 1024 * 1024:
                errors.append(f"Fayl {MAX_MB} MB dan oshmasin.")
        elif asset_id:
            from apps.content.models import ContentAsset
            asset = ContentAsset.objects.filter(pk=asset_id).exclude(file="").first()
            if not asset:
                errors.append("Tanlangan fayl topilmadi.")
            else:
                src_name = asset.original_name or asset.file.name
        else:
            errors.append("Rasm yoki video tanlang (kompyuterdan yoki kontent bazadan).")
        when = _parse_when(request, errors)
        if P.get("preflight") == "skip" and chosen and not errors:
            bad = {x["id"] for x in services.states(chosen, when) if x["problem"]}
            chosen = [a for a in chosen if a.pk not in bad]
            if not chosen:
                errors.append("Tayyor akkaunt qolmadi. Vaqtni o'zgartiring yoki akkauntlarni tekshiring.")
        track, m_start, m_len = None, 0, 0
        if P.get("music_id") and music.enabled():
            track = _find_track(P.get("music_id"), P.get("music_q", ""))
            if not track:
                errors.append("Tanlangan qo'shiq topilmadi. Musiqa ro'yxatini yangilab, qayta tanlang.")
            else:
                m_len = music.clamp_len(P.get("music_len"))
                m_start = max(0, min(int(float(P.get("music_start") or 0)) if (P.get("music_start") or "0").replace(".", "", 1).isdigit() else 0, max(0, track["duration"] - m_len)))
                if bool(get_setting("music.jamendo.credit", True)):
                    credit = music.credit_line(track["name"], track["artist"])
                    caption = (caption + "\n\n" + credit).strip() if caption else credit
                    if services.plain_len(caption) > services.CAPTION_PREMIUM:
                        errors.append("Sarlavha + musiqa muallifi qatori juda uzun.")
        if not errors:
            story = Story(title=title or (caption[:60] if caption else f"Story {timezone.localtime(timezone.now(), tz()):%d.%m %H:%M}"), caption=caption, kind=services.kind_of(src_name),
                          fit_mode=fit, period=period, privacy=privacy, pinned=P.get("pinned") == "1", noforwards=P.get("noforwards") == "1", link_url=link, reaction=reaction,
                          geo_lat=lat, geo_lon=lon, scheduled_at=when, created_by=request.user)
            if up:
                story.media.save(up.name, up, save=False)
            else:
                with open(asset.file.path, "rb") as fh:
                    story.media.save(src_name.rsplit("/", 1)[-1], File(fh), save=False)
            story.save()
            if track:   # musiqali video orqa fonda (worker) tayyorlanadi, keyin akkauntlarga navbat qo'yiladi
                story.music_track, story.music_title, story.music_artist = track["id"][:40], track["name"][:200], track["artist"][:200]
                story.music_license, story.music_start, story.music_len = track.get("license", "")[:300], m_start, m_len
                story.music_src = track["audio"][:600] if str(track["audio"]).startswith(("https://", "fake://")) else ""
                story.status = "preparing"
                story.save()
                enqueue("story_prepare", {"story_id": story.pk, "accounts": [a.pk for a in chosen], "when": when.isoformat() if when else None},
                        queue="publish", max_attempts=1, dedupe_key=f"story_prep:{story.pk}")
                audit("stories.created", user=request.user, target=story.title, detail={"accounts": len(chosen), "music": True})
                messages.success(request, "Story qabul qilindi. Musiqali video orqa fonda tayyorlanmoqda, tayyor bo'lgach akkauntlarga navbat qo'yiladi. Holatni shu sahifada kuzating.")
                return redirect("stories_detail", pk=story.pk)
            services.schedule(story, chosen, when)
            audit("stories.created", user=request.user, target=story.title, detail={"accounts": len(chosen)})
            messages.success(request, f"Story navbatga qo'yildi: {len(chosen)} ta akkaunt. Akkauntlar orasida avtomatik 1–3 daqiqa oraliq bor.")
            return redirect("stories_detail", pk=story.pk)
    pre = request.GET.get("date", "")
    default_when = f"{pre}T12:00" if len(pre) == 10 else ""
    return render(request, "stories_new.html", _ctx(request, "stories_new", title="Yangi story", accs=accs, periods=PERIODS, privacy=PRIVACY, reactions=REACTIONS[1:], assets=_assets(),
                                                   errors=errors, P=P, sel=set(request.POST.getlist("accounts")), default_when=default_when, lo_hi=services.gap_seconds(), **_music_ctx()))


# ───────────────────────── tafsilot ─────────────────────────
@login_required
@require_permission("stories.view")
def stories_detail(request, pk):
    s = get_object_or_404(Story, pk=pk)
    targets = list(s.targets.select_related("account").prefetch_related("snapshots"))
    prem = [t.account.name for t in targets if t.error_code == "premium"]
    other_err = [t for t in targets if t.status == "error" and t.error_code != "premium"]
    row = _story_row(s)
    return render(request, "stories_detail.html", _ctx(request, "stories_home", title=s.title, s=s, targets=targets, row=row, prem=prem, other_err=other_err,
                                                      period_label=dict(PERIODS).get(s.period, f"{s.period // 3600} soat"), privacy_label=dict(PRIVACY).get(s.privacy, s.privacy),
                                                      ERR=ERR_UZ, BADGE=BADGE, pending=sum(1 for t in targets if t.status == "pending")))


@login_required
def stories_media(request, pk):
    from apps.accounts.services import perms
    if not perms.can(request.user, "stories.view", None):
        raise Http404
    s = get_object_or_404(Story, pk=pk)
    try:
        return FileResponse(s.media.open("rb"), content_type=mimetypes.guess_type(s.media.name)[0] or "application/octet-stream")
    except (FileNotFoundError, ValueError):
        raise Http404 from None


@login_required
def stories_asset(request, pk):
    """Kontent bazadagi faylni oldindan ko'rish uchun (nusxa olinmaydi)."""
    from apps.accounts.services import perms
    from apps.content.models import ContentAsset
    if not perms.can(request.user, "stories.create", None):
        raise Http404
    a = ContentAsset.objects.filter(pk=pk, kind__in=["image", "video"]).exclude(file="").first()
    if not a:
        raise Http404
    try:
        return FileResponse(a.file.open("rb"), content_type=mimetypes.guess_type(a.file.name)[0] or "application/octet-stream")
    except (FileNotFoundError, ValueError):
        raise Http404 from None


@login_required
@require_POST
@require_permission("stories.edit")
def stories_action(request, pk):
    s = get_object_or_404(Story, pk=pk)
    act = request.POST.get("action")
    if act == "cancel":
        n = services.cancel(s)
        messages.success(request, f"{n} ta kutilayotgan yuborish to'xtatildi. Joylanganlar o'zgarmaydi.")
    elif act == "retry":
        t = get_object_or_404(StoryTarget, pk=request.POST.get("target"), story=s)
        services.retry_target(t)
        messages.info(request, "Qayta urinish navbatga qo'yildi.")
    elif act == "retry_all":
        n = 0
        for t in s.targets.filter(status="error").exclude(error_code="premium"):
            services.retry_target(t)
            n += 1
        messages.info(request, f"{n} ta xato qayta navbatga qo'yildi (Premium talab qilganlar o'tkazib yuborildi).")
    elif act == "stats":
        n = 0
        for t in s.targets.filter(status="sent"):
            enqueue("story_stats", {"target_id": t.pk}, queue="publish", dedupe_key=f"story_stats_now:{t.pk}", max_attempts=1)
            n += 1
        messages.info(request, f"{n} ta akkaunt statistikasi yangilanmoqda (bir necha daqiqada ko'rinadi).")
    return redirect("stories_detail", pk=s.pk)


# ───────────────────────── kalendar ─────────────────────────
@login_required
@require_permission("stories.view")
def stories_calendar(request):
    today = local(timezone.now()).date()
    try:
        y, m = (int(x) for x in (request.GET.get("m") or f"{today.year}-{today.month}").split("-"))
        first = date(y, m, 1)
    except (ValueError, TypeError):
        first = today.replace(day=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    lo = datetime.combine(first - timedelta(days=7), datetime.min.time(), tzinfo=tz())
    hi = datetime.combine(nxt + timedelta(days=7), datetime.min.time(), tzinfo=tz())
    by_day: dict[date, list] = {}
    for s in Story.objects.filter(scheduled_at__gte=lo, scheduled_at__lt=hi).prefetch_related("targets").order_by("scheduled_at"):
        r = _story_row(s)
        r["time"] = local(s.scheduled_at).strftime("%H:%M")
        by_day.setdefault(local(s.scheduled_at).date(), []).append(r)
    weeks = [[{"d": d, "in": d.month == first.month, "today": d == today, "items": by_day.get(d, [])} for d in w] for w in pycal.Calendar(0).monthdatescalendar(first.year, first.month)]
    from apps.core.utils import UZ_MONTHS
    return render(request, "stories_calendar.html", _ctx(request, "stories_calendar", title="Stories kalendari", weeks=weeks, month_name=f"{UZ_MONTHS[first.month].capitalize()} {first.year}",
                                                        prev=f"{prev.year}-{prev.month}", nxt=f"{nxt.year}-{nxt.month}", wd=["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]))


# ───────────────────────── statistika ─────────────────────────
@login_required
@require_permission("stories.view")
def stories_stats(request):
    days = 30
    since = timezone.now() - timedelta(days=days)
    rows = []
    for a in StoryAccount.objects.all():
        t = a.targets.filter(sent_at__gte=since)
        ok = t.filter(status="sent")
        agg = ok.aggregate(n=Count("id"), v=Sum("views"), f=Sum("forwards"), r=Sum("reactions"))
        n = agg["n"] or 0
        rows.append({"a": a, "sent": n, "err": a.targets.filter(status="error", story__created_at__gte=since).count(), "views": agg["v"] or 0,
                     "avg": round((agg["v"] or 0) / n) if n else 0, "fw": agg["f"] or 0, "re": agg["r"] or 0})
    rows.sort(key=lambda r: -r["views"])
    top = []
    for s in Story.objects.filter(created_at__gte=since).prefetch_related("targets"):
        r = _story_row(s)
        if r["sent"]:
            top.append(r)
    top.sort(key=lambda r: -r["views"])
    totals = {"sent": sum(r["sent"] for r in rows), "views": sum(r["views"] for r in rows), "fw": sum(r["fw"] for r in rows), "re": sum(r["re"] for r in rows)}
    return render(request, "stories_stats.html", _ctx(request, "stories_stats", title="Stories statistikasi", rows=rows, top=top[:15], totals=totals, days=days))
