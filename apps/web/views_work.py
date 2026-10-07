"""Kundalik ish vositalari: karusel tartibi, kalendarda ko'chirish, nusxa, shablonlar, vazifa/izohlar, umumiy qidiruv."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.models import User
from apps.accounts.services import perms
from apps.content import state, workflow
from apps.content.models import ContentAsset, ContentItem, ContentTarget, PostTemplate
from apps.core.audit import audit
from apps.core.utils import fmt_dt, tz
from . import ui
from .common import get_obj


# ---------------------------------------------------------------- karusel tartibi
def normalize_positions(item) -> list:
    arr = list(item.assets.order_by("position", "id"))
    for i, a in enumerate(arr):
        if a.position != i:
            a.position = i
            a.save(update_fields=["position"])
    return arr


@login_required
@require_POST
def content_asset_move(request, pk, aid):
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    if item.status == "publishing":
        messages.error(request, "Nashr jarayonida tartib o'zgarmaydi.")
        return redirect("content_detail", pk=item.pk)
    arr = normalize_positions(item)
    ids = [a.pk for a in arr]
    if aid not in ids:
        return redirect("content_detail", pk=item.pk)
    i, step = ids.index(aid), (-1 if request.POST.get("dir") == "up" else 1)
    j = i + step
    if 0 <= j < len(arr):
        arr[i].position, arr[j].position = arr[j].position, arr[i].position
        arr[i].save(update_fields=["position"])
        arr[j].save(update_fields=["position"])
        audit("content.media_order", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title})
        state.on_item_edited(item, request.user)
    return redirect("content_detail", pk=item.pk)


# ---------------------------------------------------------------- kalendarda sudrab ko'chirish
@login_required
@require_POST
def content_move(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    if item.status in ("published", "publishing"):
        return JsonResponse({"ok": False, "error": "Chiqarilgan yoki nashr bo'layotgan postni ko'chirib bo'lmaydi."}, status=400)
    try:
        d = date.fromisoformat(request.POST.get("date", ""))
    except ValueError:
        return JsonResponse({"ok": False, "error": "Sana noto'g'ri."}, status=400)
    z = tz()
    old = item.scheduled_at.astimezone(z) if item.scheduled_at else None
    hh, mm = (old.hour, old.minute) if old else (12, 0)
    new = datetime(d.year, d.month, d.day, hh, mm, tzinfo=z)
    if new < timezone.now() - timedelta(minutes=1):
        return JsonResponse({"ok": False, "error": "O'tib ketgan vaqtga ko'chirib bo'lmaydi."}, status=400)
    item.scheduled_at = new
    item.save(update_fields=["scheduled_at", "updated_at"])
    res = state.on_item_edited(item, request.user)
    audit("content.move", user=request.user, business_id=item.business_id, target=f"item:{item.pk}",
          detail={"title": item.title, "to": new.strftime("%Y-%m-%d %H:%M")})
    return JsonResponse({"ok": True, "when": fmt_dt(new), "status": item.status, "note": res if res not in ("", "scheduled", "draft") else ""})


# ---------------------------------------------------------------- nusxa
@login_required
@require_POST
def content_duplicate(request, pk):
    src = get_obj(request, ContentItem, pk, "calendar.view")
    if not perms.can(request.user, "calendar.create", src.business):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    new = ContentItem.objects.create(business=src.business, title=(src.title + " (nusxa)")[:200], text=src.text, media_type=src.media_type, status="draft",
                                     created_by=request.user, options=dict(src.options or {}), notes=src.notes, brief=src.brief, hook_idea=src.hook_idea, cta=src.cta, goal=src.goal)
    for t in src.targets.all():
        ContentTarget.objects.get_or_create(item=new, account=t.account)
    for a in src.assets.order_by("position", "id"):
        try:
            data = a.file.read() if a.file else b""
            a.file.close()
        except Exception:  # noqa: BLE001
            continue
        na = ContentAsset(item=new, kind=a.kind, original_name=a.original_name, size=len(data), sha256=hashlib.sha256(data).hexdigest(), cloud=a.cloud, position=a.position)
        na.file.save(a.original_name or "fayl", ContentFile(data), save=True)
    audit("content.duplicate", user=request.user, business_id=new.business_id, target=f"item:{new.pk}", detail={"title": new.title})
    messages.success(request, "Nusxa qoralama sifatida yaratildi. Vaqtini belgilang.")
    return redirect("content_edit", pk=new.pk)


# ---------------------------------------------------------------- shablonlar
VARS_HELP = "{sana} — nashr sanasi, {kun} — hafta kuni, {biznes} — biznes nomi"
WD = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]


def fill_vars(text: str, business, when: date | None) -> str:
    when = when or timezone.localdate()
    return (text or "").replace("{sana}", when.strftime("%d.%m.%Y")).replace("{kun}", WD[when.weekday()]).replace("{biznes}", business.name)


def _next_weekday(wd: int) -> date:
    t = timezone.localdate()
    return t + timedelta(days=(wd - t.weekday()) % 7)


def template_files(tpl: PostTemplate) -> list[dict]:
    """Shablonga biriktirilgan Cloudflare fayllari (hali mavjudlari)."""
    from apps.content import temphost
    from apps.content.models import TempObject
    ids = [int(x) for x in (tpl.options or {}).get("cloud_ids") or [] if str(x).isdigit()]
    out = []
    for o in TempObject.objects.filter(pk__in=ids, status="uploaded").filter(Q(business=tpl.business) | Q(item__business=tpl.business)):
        ext = (o.filename or o.key).rsplit(".", 1)[-1].lower()
        out.append({"id": o.pk, "name": o.filename or o.key, "kind": "video" if ext in ("mp4", "mov", "m4v", "webm") else "image", "url": temphost.view_url(o)})
    order = {i: n for n, i in enumerate(ids)}
    return sorted(out, key=lambda x: order.get(x["id"], 0))


def template_initial(tpl: PostTemplate, business, accounts, when: date | None = None) -> dict:
    o = tpl.options or {}
    wd = o.get("weekday")
    if when is None and isinstance(wd, int) and 0 <= wd <= 6:
        when = _next_weekday(wd)
    ini = {"title": fill_vars(tpl.title, business, when), "text": fill_vars(tpl.text, business, when), "media_type": tpl.media_type,
           "brief": tpl.brief, "yt_title": fill_vars(o.get("title", ""), business, when), "yt_tags": ", ".join(o.get("tags") or []),
           "yt_privacy": o.get("privacy", "public"), "media_size": o.get("media_size", "orig"), "fit_mode": o.get("fit_mode", "pad"),
           "tg_buttons": __import__("apps.web.forms", fromlist=["buttons_to_text"]).buttons_to_text(o.get("buttons") or []),
           "tg_cols": str(o.get("btn_cols") or 2)}
    if tpl.platform:
        ini["targets"] = [str(a.pk) for a in accounts if a.platform == tpl.platform]
    if when and tpl.time_hint:
        ini["scheduled_at"] = f"{when.isoformat()}T{tpl.time_hint}"
    elif when:
        ini["scheduled_at"] = f"{when.isoformat()}T12:00"
    return {k: v for k, v in ini.items() if v not in (None, "")}


@login_required
@require_POST
def template_from_item(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.create")
    name = (request.POST.get("name") or item.title or "Shablon").strip()[:120]
    o = dict(item.options or {})
    o.pop("crop", None)
    plats = {t.account.platform for t in item.targets.select_related("account")}
    t = PostTemplate.objects.create(business=item.business, name=name, platform=next(iter(plats)) if len(plats) == 1 else "", media_type=item.media_type,
                                    title=item.title, text=item.text, brief=item.brief, options=o,
                                    time_hint=item.scheduled_at.astimezone(tz()).strftime("%H:%M") if item.scheduled_at else "", created_by=request.user)
    audit("template.create", user=request.user, business_id=item.business_id, target=f"tpl:{t.pk}", detail={"name": name})
    messages.success(request, f"«{name}» shabloni saqlandi. Kalendar → Shablonlar bo'limida topasiz.")
    return redirect("content_detail", pk=item.pk)


def _tpl_row(t: PostTemplate, request) -> dict:
    from apps.web.forms import ALLOWED_TYPES, buttons_to_text
    o = t.options or {}
    wd = o.get("weekday")
    return {"id": t.pk, "name": t.name, "business": t.business.name, "platform": t.platform, "media_type": t.media_type, "title": t.title, "text": t.text,
            "brief": t.brief, "time_hint": t.time_hint, "weekday": wd if isinstance(wd, int) else "", "uses": t.uses,
            "tg_buttons": buttons_to_text(o.get("buttons") or []), "tg_cols": str(o.get("btn_cols") or 2),
            "yt_title": o.get("title", ""), "yt_tags": ", ".join(o.get("tags") or []), "yt_privacy": o.get("privacy", "public"),
            "files": template_files(t), "can_edit": perms.can(request.user, "calendar.edit", t.business), "can_delete": perms.can(request.user, "calendar.delete", t.business)}


@login_required
@require_permission("calendar.view")
def template_list(request):
    from apps.web.forms import ALLOWED_TYPES
    from . import spa
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "calendar.view").values_list("pk", flat=True))
    qs = PostTemplate.objects.filter(business_id__in=ids).select_related("business")
    can_c = bool(request.business) and perms.can(request.user, "calendar.create", request.business)
    return spa.respond(request, {"kind": "templates", "rows": [_tpl_row(t, request) for t in qs], "can_create": can_c, "vars_help": VARS_HELP,
                                 "allowed": {k: list(v) for k, v in ALLOWED_TYPES.items()}, "weekdays": WD, "has_business": bool(request.business)})


def _tpl_apply(request, t: PostTemplate) -> str:
    """POST ma'lumotlarini shablonga yozadi; xato bo'lsa matn qaytaradi."""
    from apps.web.forms import ALLOWED_TYPES, parse_buttons
    from apps.content.models import TempObject
    P = request.POST
    name = (P.get("name") or "").strip()[:120]
    if not name:
        return "Shablon nomini kiriting."
    plat = P.get("platform", "")
    if plat and plat not in ALLOWED_TYPES:
        return "Platforma noto'g'ri."
    mt = P.get("media_type", "text")
    if plat and mt not in ALLOWED_TYPES[plat]:
        return f"«{plat.title()}» uchun bu post turi mumkin emas."
    hint = (P.get("time_hint") or "").strip()
    if hint:
        try:
            datetime.strptime(hint, "%H:%M")
        except ValueError:
            return "Vaqt HH:MM ko'rinishida bo'lsin (masalan 10:00)."
    o = dict(t.options or {})
    for k in ("title", "tags", "privacy", "buttons", "btn_cols", "weekday", "cloud_ids"):
        o.pop(k, None)
    if (P.get("yt_title") or "").strip():
        o["title"] = P["yt_title"].strip()[:100]
    tags = [x.strip() for x in (P.get("yt_tags") or "").split(",") if x.strip()]
    if tags:
        o["tags"] = tags[:30]
    if P.get("yt_privacy"):
        o["privacy"] = P["yt_privacy"]
    cols = P.get("tg_cols") if P.get("tg_cols") in ("1", "2", "3") else "2"
    rows = parse_buttons(P.get("tg_buttons", ""), int(cols)) if (P.get("tg_buttons") or "").strip() else []
    if rows:
        o["buttons"], o["btn_cols"] = rows, int(cols)
    if P.get("weekday", "").isdigit() and 0 <= int(P["weekday"]) <= 6:
        o["weekday"] = int(P["weekday"])
    ids = [int(x) for x in P.getlist("cloud_ids") if x.isdigit()]
    ok = set(TempObject.objects.filter(pk__in=ids, status="uploaded").filter(Q(business=t.business) | Q(item__business=t.business)).values_list("pk", flat=True))
    ids = [i for i in ids if i in ok][:10]
    if ids:
        o["cloud_ids"] = ids
    t.name, t.platform, t.media_type, t.title, t.text, t.brief, t.time_hint, t.options = name, plat, mt, (P.get("title") or "").strip()[:200], P.get("text", ""), P.get("brief", ""), hint, o
    return ""


@login_required
@require_POST
def template_save(request, pk=None):
    if pk:
        t = get_obj(request, PostTemplate, pk, "calendar.edit")
    else:
        if not request.business:
            messages.error(request, "Avval biznesni tanlang.")
            return redirect("template_list")
        if not perms.can(request.user, "calendar.create", request.business):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        t = PostTemplate(business=request.business, created_by=request.user)
    err = _tpl_apply(request, t)
    if err:
        messages.error(request, err)
        return redirect("template_list")
    t.save()
    audit("template.update" if pk else "template.create", user=request.user, business_id=t.business_id, target=f"tpl:{t.pk}", detail={"name": t.name})
    messages.success(request, f"«{t.name}» shabloni saqlandi.")
    return redirect("template_list")


@login_required
@require_POST
def template_delete(request, pk):
    t = get_obj(request, PostTemplate, pk, "calendar.delete")
    audit("template.delete", user=request.user, business_id=t.business_id, target=f"tpl:{t.pk}", detail={"name": t.name})
    t.delete()
    messages.success(request, "Shablon o'chirildi.")
    return redirect("template_list")


# ---------------------------------------------------------------- vazifa / izoh
def _parse_due(s: str):
    s = (s or "").strip()
    if not s:
        return None
    for f in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, f).replace(tzinfo=tz())
        except ValueError:
            pass
    return None


@login_required
@require_POST
def task_set(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    uid = request.POST.get("assignee", "")
    a = User.objects.filter(pk=uid, is_active=True).first() if uid.isdigit() else None
    if a and not perms.has_business(a, item.business_id):
        messages.error(request, "Bu xodimning shu biznesga kirishi yo'q.")
        return redirect("content_detail", pk=item.pk)
    workflow.assign_task(item, request.user, assignee=a, due_at=_parse_due(request.POST.get("due_at")), brief=request.POST.get("brief", ""))
    messages.success(request, "Vazifa saqlandi." + (" Xodimga bildirishnoma yuborildi." if a else ""))
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def task_status(request, pk, new):
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    if new in ("revision", "accepted") and not (perms.can(request.user, "calendar.create", item.business) or request.user.is_admin):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if workflow.set_status(item, request.user, new, request.POST.get("note", "")):
        messages.success(request, "Holat yangilandi: " + workflow.DESIGN_STATUS[new])
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def item_comment(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.view")
    if workflow.comment(item, request.user, request.POST.get("text", "")):
        messages.success(request, "Izoh qo'shildi.")
    return redirect(f"/kalendar/{item.pk}/#izohlar")


@login_required
@require_permission("calendar.view")
def my_tasks(request):
    u = request.user
    ids = [request.business.pk] if request.business else list(perms.businesses_for(u, "calendar.view").values_list("pk", flat=True))
    base = ContentItem.objects.filter(business_id__in=ids).select_related("business", "assignee")
    now = timezone.now()

    def row(it):
        late = bool(it.due_at and it.due_at < now and it.design_status in workflow.OPEN)
        return [ui.link(it.title or "(nomsiz)", f"/kalendar/{it.pk}/"), it.business.name, ui.badge(workflow.DESIGN_STATUS.get(it.design_status, "—"), None),
                (ui.badge("Muddat o'tgan: " + fmt_dt(it.due_at), "failed") if late else ui.dt(it.due_at)), it.assignee.display() if it.assignee else "—",
                (it.brief or "")[:80]]
    cols = ["Post", "Biznes", "Holat", "Muddat", "Mas'ul", "Topshiriq"]
    mine = base.filter(assignee=u, design_status__in=workflow.OPEN).order_by("due_at", "-updated_at")
    review = base.filter(design_status="ready").exclude(assignee=u).order_by("-updated_at") if perms.businesses_for(u, "calendar.create").exists() or u.is_admin else base.none()
    allopen = base.filter(design_status__in=workflow.OPEN).exclude(assignee=u).order_by("due_at")[:50] if perms.businesses_for(u, "calendar.create").exists() or u.is_admin else base.none()
    blocks = [ui.table("Mening vazifalarim", cols, [row(i) for i in mine], empty="Sizga biriktirilgan ochiq vazifa yo'q."),
              ui.table("Tayyor — ko'rib chiqishingiz kerak", cols, [row(i) for i in review[:50]], empty="Ko'rib chiqishni kutayotgan ish yo'q."),
              ui.table("Boshqalardagi ochiq vazifalar", cols, [row(i) for i in allopen], empty="Ochiq vazifa yo'q.")]
    return ui.page(request, "Vazifalar", blocks, subtitle="Dizayner/kontent-maker ish oqimi: topshiriq → jarayonda → tayyor → qabul")


# ---------------------------------------------------------------- umumiy qidiruv
@login_required
def global_search(request):
    q = (request.GET.get("q") or "").strip()
    u = request.user
    if len(q) < 2:
        return ui.page(request, "Qidiruv", [{"type": "text", "text": "Kamida 2 ta belgi yozing. Postlar, Cloudflare fayllari, g'oyalar, ssenariylar, raqobatchilar va lidlar bo'yicha qidiriladi."}])
    ids = [request.business.pk] if request.business else list(perms.businesses_for(u).values_list("pk", flat=True))
    blocks = []
    L = 15
    if perms.businesses_for(u, "calendar.view").exists():
        qs = ContentItem.objects.filter(business_id__in=ids).filter(Q(title__icontains=q) | Q(text__icontains=q) | Q(notes__icontains=q) | Q(hook_idea__icontains=q) | Q(cta__icontains=q) | Q(brief__icontains=q)).select_related("business").order_by("-updated_at")[:L]
        blocks.append(ui.table(f"Postlar ({len(qs)})", ["Post", "Biznes", "Holat", "Vaqt"],
                               [[ui.link(i.title or "(nomsiz)", f"/kalendar/{i.pk}/", (i.text or "")[:80]), i.business.name, i.get_status_display(), ui.dt(i.scheduled_at)] for i in qs], empty="Mos post topilmadi."))
        from apps.metrics.models import Post
        ps = Post.objects.filter(business_id__in=ids, text__icontains=q).select_related("account").order_by("-published_at")[:L]
        if ps:
            blocks.append(ui.table(f"Chiqqan postlar ({len(ps)})", ["Matn", "Platforma", "Sana", ""],
                                   [[(p.text or "")[:100], p.platform.title(), ui.dt(p.published_at), ui.link("Tahlil", f"/tahlil/post/{p.pk}/")] for p in ps]))
    if perms.businesses_for(u, "publish.view").exists():
        from apps.content.models import TempObject
        fs = TempObject.objects.filter(business_id__in=ids, status="uploaded").filter(Q(filename__icontains=q) | Q(tags__icontains=q))[:L]
        if fs:
            blocks.append(ui.table(f"Cloudflare fayllari ({len(fs)})", ["Fayl", "Teglar", "Hajmi", ""],
                                   [[f.filename or f.key, f.tags or "—", f"{(f.size or 0) // 1024} KB", ui.link("Ochish", "/cloudflare/")] for f in fs]))
    try:
        from apps.studio.models import Idea, Script
        if perms.businesses_for(u, "ai_studio.view").exists():
            ideas = Idea.objects.filter(business_id__in=ids).filter(Q(title__icontains=q) | Q(hook__icontains=q) | Q(angle__icontains=q) | Q(script_text__icontains=q)).order_by("-created_at")[:L]
            if ideas:
                blocks.append(ui.table(f"G'oyalar ({len(ideas)})", ["G'oya", "Platforma", "Holat"], [[ui.link(i.title, f"/goyalar/{i.pk}/"), i.platform.title() or "—", i.get_status_display()] for i in ideas]))
            sc = Script.objects.filter(business_id__in=ids).filter(Q(title__icontains=q) | Q(raw_text__icontains=q) | Q(brief__icontains=q)).order_by("-id")[:L]
            if sc:
                blocks.append(ui.table(f"Ssenariylar ({len(sc)})", ["Ssenariy"], [[ui.link(str(s), f"/studiya/ssenariy/{s.pk}/")] for s in sc]))
    except Exception:  # noqa: BLE001
        pass
    if perms.businesses_for(u, "competitors.view").exists():
        from apps.connections.models import Competitor
        cs = Competitor.objects.filter(business_id__in=ids).filter(Q(name__icontains=q) | Q(handle__icontains=q))[:L]
        if cs:
            blocks.append(ui.table(f"Raqobatchilar ({len(cs)})", ["Nomi", "Platforma"], [[ui.link(c.name or c.handle, f"/raqobatchilar/{c.pk}/"), c.platform.title()] for c in cs]))
    if not blocks:
        blocks = [{"type": "text", "text": "Hech narsa topilmadi."}]
    return ui.page(request, f"Qidiruv: {q}", blocks)
