from __future__ import annotations

import hashlib
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.connections.models import SocialAccount
from apps.content import services as csvc
from apps.content import state
from apps.content.models import STATUSES, ContentAsset, ContentItem, ContentTarget, PublishAttempt
from apps.core.audit import audit
from apps.web.views_activity import history_for_item
from apps.metrics import analytics as an
from apps.metrics.models import Post
from . import spa, ui
from .common import get_obj
from .forms import ALLOWED_TYPES, AssetForm, ContentForm


def _items(request, code="calendar.view"):
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, code).values_list("pk", flat=True))
    return ContentItem.objects.filter(business_id__in=ids).select_related("business")


@login_required
@require_permission("calendar.view")
def calendar(request):
    qs = _items(request)
    st = request.GET.get("status")
    if st:
        qs = qs.filter(status=st)
    pf, ff = request.GET.get("p", ""), request.GET.get("f", "")
    if pf in ("telegram", "instagram", "youtube"):
        qs = qs.filter(targets__account__platform=pf).distinct()
    if ff:
        qs = qs.filter(media_type=ff)
    m = request.GET.get("m")
    try:
        y, mo = (int(x) for x in m.split("-")) if m else (timezone.localdate().year, timezone.localdate().month)
    except ValueError:
        y, mo = timezone.localdate().year, timezone.localdate().month
    first = date(y, mo, 1)
    nxt = date(y + (mo == 12), mo % 12 + 1, 1)
    prev = (first - timedelta(days=1)).replace(day=1)
    from datetime import datetime as _dt
    from apps.core.utils import tz as _z
    lo, hi = _dt.combine(first, _dt.min.time(), tzinfo=_z()), _dt.combine(nxt, _dt.min.time(), tzinfo=_z())   # MySQL'da vaqt jadvallari (CONVERT_TZ) bo'lmasligi mumkin
    scheduled = qs.filter(scheduled_at__gte=lo, scheduled_at__lt=hi).order_by("scheduled_at").prefetch_related("targets__account", "assets")
    scheduled = list(scheduled)
    unsched = list(qs.filter(scheduled_at__isnull=True).exclude(status="published")[:30])
    from apps.core.utils import tz as _tz
    days: dict = {}
    for i in scheduled:
        th = next((a.pk for a in i.assets.all() if a.kind == "image"), None)
        days.setdefault(i.scheduled_at.astimezone(_tz()).date().isoformat(), []).append(_cal_item(i, th))
    can_move = bool(request.business) and perms.can(request.user, "calendar.edit", request.business)
    fmts = {"telegram": ["text", "image", "video", "album"], "instagram": ["image", "carousel", "reel", "story"], "youtube": ["video", "short"]}.get(pf, [])
    return spa.respond(request, {
        "kind": "calendar", "month": f"{first:%Y-%m}", "prev": f"{prev:%Y-%m}", "next": f"{nxt:%Y-%m}", "today": timezone.localdate().isoformat(),
        "f": {"status": st or "", "p": pf, "f": ff}, "statuses": [[k, v] for k, v in STATUSES if k not in ("pending_approval", "approved")],
        "formats": fmts, "days": days, "can_create": bool(request.business), "can_move": can_move,
        "unscheduled": [_cal_item(i, None, with_biz=True) for i in unsched], "can_autotime": bool(unsched and request.business),
        "list": [_cal_item(i, None, with_biz=True) for i in scheduled]})


def _cal_item(i, th, with_biz=False):
    from apps.core.utils import tz as _tz
    d = {"id": i.pk, "title": i.title or "(nomsiz)", "status": i.status, "status_label": i.get_status_display(), "format": i.get_media_type_display(), "type": i.media_type,
         "platforms": sorted({PLAT_ICON.get(t.account.platform, "?") for t in i.targets.all()}), "rule": i.rule_status or "",
         "time": i.scheduled_at.astimezone(_tz()).strftime("%H:%M") if i.scheduled_at else "", "when": ui.dt(i.scheduled_at),
         "thumb": f"/kalendar/{i.pk}/media/{th}/" if th else ""}
    if with_biz:
        d["business"] = i.business.name
    return d


PLAT_ICON = {"telegram": "TG", "instagram": "IG", "youtube": "YT"}


def _trashed(request, pk, code):
    item = ContentItem.all_objects.filter(pk=pk, deleted_at__isnull=False).select_related("business").first()
    if item is None or not perms.has_business(request.user, item.business_id):
        from django.http import Http404
        raise Http404
    if not perms.can(request.user, code, item.business):
        raise PermissionDenied
    return item


@login_required
@require_POST
def content_delete(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.delete")
    if item.status == "publishing":
        messages.error(request, "Post hozir nashr qilinmoqda — tugagach o'chiring.")
        return redirect("content_detail", pk=item.pk)
    was_live = item.status == "published"
    new_status = "draft" if item.status in ("scheduled", "failed") else item.status
    ContentItem.all_objects.filter(pk=item.pk).update(deleted_at=timezone.now(), deleted_by=request.user, status=new_status)
    audit("content.delete", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title})
    messages.success(request, f"«{item.title}» savatga o'tkazildi (30 kun ichida tiklash mumkin)." + (" Platformada chiqqan post o'chmaydi — uni o'zingiz o'chiring." if was_live else ""))
    return redirect("calendar")


@login_required
@require_POST
def content_delete_many(request):
    ids = [int(x) for x in request.POST.getlist("ids") if x.isdigit()]
    n = 0
    for item in _items(request, "calendar.delete").filter(pk__in=ids).exclude(status="publishing"):
        if not perms.can(request.user, "calendar.delete", item.business):
            continue
        ContentItem.all_objects.filter(pk=item.pk).update(deleted_at=timezone.now(), deleted_by=request.user, status="draft" if item.status in ("scheduled", "failed") else item.status)
        n += 1
    messages.success(request, f"{n} ta post savatga o'tkazildi.") if n else messages.info(request, "Hech narsa tanlanmadi.")
    return redirect(request.POST.get("next") or "calendar")


@login_required
@require_permission("calendar.view")
def trash_list(request):
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "calendar.view").values_list("pk", flat=True))
    items = ContentItem.all_objects.filter(business_id__in=ids, deleted_at__isnull=False).select_related("business", "deleted_by").order_by("-deleted_at")
    rows = []
    for i in items[:200]:
        left = max(0, 30 - (timezone.now() - i.deleted_at).days)
        rows.append([i.title or "(nomsiz)", i.business.name, i.get_media_type_display(), i.get_status_display(), ui.dt(i.deleted_at), f"{left} kun",
                     ui.btn("Tiklash", f"/kalendar/savat/{i.pk}/tiklash/", "primary"), ui.btn("Butunlay o'chirish", f"/kalendar/savat/{i.pk}/ochir/", "danger", "Post butunlay o'chiriladi va tiklab bo'lmaydi. Davom etasizmi?")])
    blocks = [ui.table("O'chirilgan postlar", ["Sarlavha", "Biznes", "Tur", "Holat", "O'chirilgan", "Qoldi", "", ""], rows, "Savat bo'sh."),
              {"type": "text", "title": "Eslatma", "text": "Savatdagi postlar 30 kundan keyin avtomatik butunlay o'chadi. Tiklangan post qoralama holatida qaytadi. Cloudflare'dagi fayllar alohida: «Fayllar (Cloudflare)» bo'limidan o'chiriladi."}]
    if rows:
        blocks.append({"type": "actions", "title": "Amallar", "buttons": [ui.btn("Savatni bo'shatish", "/kalendar/savat/bosh/", "danger", "Savatdagi hamma post butunlay o'chadi. Davom etasizmi?")]})
    return ui.page(request, "Savat", blocks, toolbar=[{"label": "Kalendarga qaytish", "url": "/kalendar/"}])


@login_required
@require_POST
def content_restore(request, pk):
    item = _trashed(request, pk, "calendar.delete")
    ContentItem.all_objects.filter(pk=item.pk).update(deleted_at=None, deleted_by=None)
    audit("content.restore", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title})
    messages.success(request, f"«{item.title}» tiklandi.")
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def content_purge(request, pk):
    item = _trashed(request, pk, "calendar.delete")
    audit("content.purge", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title})
    item.delete()
    messages.success(request, "Post butunlay o'chirildi.")
    return redirect("trash_list")


@login_required
@require_POST
def trash_empty(request):
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "calendar.delete").values_list("pk", flat=True))
    qs = ContentItem.all_objects.filter(business_id__in=ids, deleted_at__isnull=False)
    n = qs.count()
    qs.delete()
    messages.success(request, f"Savat bo'shatildi ({n} ta post).")
    return redirect("trash_list")


def _form(request, item=None, data=None, initial=None, platform=None):
    biz = item.business if item else request.business
    accs = SocialAccount.objects.filter(business=biz, archived_at__isnull=True)
    if platform:
        accs = accs.filter(platform=platform)
    return ContentForm(data, instance=item, accounts=accs, initial=initial)


PLATFORM_INFO = {
    "telegram": {"name": "Telegram", "types": "Matn, Rasm, Video, Albom", "tips": [
        "Matn media bilan 1024 belgigacha (caption), mediasiz 4096 belgi.", "Bot orqali video 50 MB gacha; kattasini avval kichraytiring.", "Tugmalar (havola) qo'shsa bo'ladi."]},
    "instagram": {"name": "Instagram", "types": "Rasm, Karusel, Reels, Stories", "tips": [
        "Lenta rasmi 4:5 (1080×1350) yoki 1:1; Reels va Stories 9:16 (1080×1920).", "Izoh 2200 belgigacha, birinchi 125 belgi eng muhim.", "Faqat Professional (Business/Creator) akkaunt.",
        "Trend audio montajda videoga qo'shiladi (API orqali musiqa biriktirib bo'lmaydi)."]},
    "youtube": {"name": "YouTube", "types": "Video, Shorts", "tips": [
        "Sarlavha ≤100 belgi, kalit so'z boshida.", "Shorts: vertikal 9:16, 3 daqiqagacha.", "Kunlik yuklash limiti bor (Sozlamalarda)."]},
}


def _plat_ctx(request, platform, item=None):
    if not platform:
        return {}
    from apps.content.insights import insights_brief
    info = PLATFORM_INFO[platform]
    biz = item.business if item else request.business
    return {"fixed": platform, "plat_info": info, "plat_brief": insights_brief(biz, platform)}


def _item_platform(item):
    p = {t.account.platform for t in item.targets.select_related("account")}
    return next(iter(p)) if len(p) == 1 else None


def _targets_ctx(form):
    """Platforma kartalari uchun: [{pk,label,platform,checked}]."""
    bound = form.data.getlist("targets") if form.is_bound else [str(x) for x in (form.fields["targets"].initial or [])]
    return [{"pk": pk, "label": label, "platform": form.account_platforms.get(pk, ""), "checked": pk in bound}
            for pk, label in form.fields["targets"].choices]


def _after_save(request, item, ok_msg: str) -> None:
    """Saqlangach: vaqt va maqsad bo'lsa avtomatik rejalashtiriladi (tasdiqlash yo'q)."""
    res = state.auto_schedule(item, request.user)
    if res == "scheduled":
        messages.success(request, f"{ok_msg} Post {ui.dt(item.scheduled_at)} (Toshkent vaqti) ga rejalashtirildi.")
    elif res == "draft":
        messages.success(request, f"{ok_msg} Vaqt olib tashlangani uchun qoralamaga qaytdi.")
    elif res:
        messages.warning(request, f"{ok_msg} Lekin rejalashtirib bo'lmadi: {res}")
    else:
        why = "vaqt belgilanmagan" if not item.scheduled_at else ("platforma tanlanmagan" if not item.targets.exists() else "")
        messages.success(request, ok_msg + (f" Qoralama sifatida saqlandi ({why})." if why and item.status == "draft" else ""))


def _media_list(item) -> list[dict]:
    return [{"url": f"/kalendar/{item.pk}/media/{a.pk}/", "kind": "video" if a.kind == "video" else "image", "name": a.original_name, "id": a.pk}
            for a in item.assets.exclude(kind="audio").order_by("position", "id")] if item and item.pk else []


def _acc_map(form):
    """Oldindan ko'rish uchun: {account_pk: {platform, name, handle}}."""
    out = {}
    for pk, _ in form.fields["targets"].choices:
        a = SocialAccount.objects.filter(pk=int(pk)).first()
        if a:
            out[pk] = {"platform": a.platform, "name": a.name, "handle": a.handle}
    return out


def _save_targets(item, ids):
    ids = {int(x) for x in ids}
    item.targets.exclude(account_id__in=ids).filter(status="pending").delete()
    for a in SocialAccount.objects.filter(pk__in=ids, business=item.business):
        ContentTarget.objects.get_or_create(item=item, account=a)


@login_required
@require_permission("calendar.create")
def content_new(request, platform=None):
    if not request.business:
        messages.info(request, "Avval biznesni tanlang.")
        return redirect("calendar")
    if platform is not None and platform not in PLATFORM_INFO:
        from django.http import Http404
        raise Http404
    tpl = None
    if request.GET.get("shablon", "").isdigit():
        from apps.content.models import PostTemplate
        tpl = PostTemplate.objects.filter(pk=int(request.GET["shablon"]), business=request.business).first()
        if tpl and platform is None and tpl.platform and request.method == "GET":
            return redirect(f"/kalendar/yangi/{tpl.platform}/?" + request.GET.urlencode())
    if platform is None and request.method == "GET":
        counts = {p: SocialAccount.objects.filter(business=request.business, platform=p, archived_at__isnull=True).count() for p in PLATFORM_INFO}
        qp = {k: request.GET[k] for k in ("date", "shablon") if request.GET.get(k)}
        from urllib.parse import urlencode
        q = ("?" + urlencode(qp)) if qp else ""
        cards = [{"key": k, "q": q, "n": counts[k], **v} for k, v in PLATFORM_INFO.items()]
        return spa.respond(request, {"kind": "content_choose", "cards": cards})
    initial = {}
    d = request.GET.get("date", "")
    try:
        initial["scheduled_at"] = f"{date.fromisoformat(d).isoformat()}T12:00" if d else None
    except ValueError:
        initial["scheduled_at"] = None
    if tpl and request.method == "GET":
        from apps.web.views_work import template_initial
        try:
            when = date.fromisoformat(d) if d else None
        except ValueError:
            when = None
        accs = SocialAccount.objects.filter(business=request.business, archived_at__isnull=True)
        if platform:
            accs = accs.filter(platform=platform)
        initial = {**initial, **template_initial(tpl, request.business, accs, when)}
    form = _form(request, data=request.POST or None, initial={k: v for k, v in initial.items() if v}, platform=platform)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.business, item.created_by = request.business, request.user
        item.options = form.options_from_cleaned(item.options)
        item.save()
        _save_targets(item, form.cleaned_data["targets"])
        _save_uploads(request, item)
        _task_after_save(request, item, None)
        if tpl:
            tpl.uses += 1
            tpl.save(update_fields=["uses"])
        _maybe_autotime(request, item, form)
        audit("content.create", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title, "type": item.media_type})
        _after_save(request, item, "Kontent yaratildi.")
        return redirect("content_detail", pk=item.pk)
    title = f"Yangi {PLATFORM_INFO[platform]['name']} kontenti" if platform else "Yangi kontent"
    return _form_response(request, form, title, "/kalendar/yangi/" if platform else "/kalendar/", platform, tpl_list=_tpl_list(request, platform))


def _form_response(request, form, title, back, platform, item=None, tpl_list=None):
    """Post formasi (yaratish/tahrirlash) uchun React'ga to'liq tavsif: forma maydonlari, akkauntlar, platforma xulosasi."""
    from apps.content.mediafit import size_choices
    ctx = _plat_ctx(request, platform, item)
    return spa.respond(request, {
        "kind": "content_form", "title": title, "back": back, "form": spa.form_schema(form), "targets": _targets_ctx(form), "acc_map": _acc_map(form),
        "existing_media": _media_list(form.instance), "fixed": ctx.get("fixed", ""), "plat_info": ctx.get("plat_info"), "plat_brief": ctx.get("plat_brief", ""),
        "tpl_list": tpl_list or [], "item_id": item.pk if item else None, "sizes": [[k, v] for k, v in size_choices()],
        "allowed": {k: list(v) for k, v in ALLOWED_TYPES.items()}, "bound": form.is_bound})


def _tpl_list(request, platform):
    from apps.content.models import PostTemplate
    qs = PostTemplate.objects.filter(business=request.business)
    if platform:
        qs = qs.filter(platform__in=[platform, ""])
    q = request.GET.get("date")
    base = f"/kalendar/yangi/{platform}/" if platform else "/kalendar/yangi/"
    return [{"name": t.name, "platform": t.platform, "url": f"{base}?shablon={t.pk}" + (f"&date={q}" if q else "")} for t in qs[:40]]


def _item_platforms(item) -> list[str]:
    return sorted({t.account.platform for t in item.targets.select_related("account")})


def _apply_autotime(item) -> dict | None:
    """Postga eng yaxshi bo'sh vaqtni qo'yadi (boshqa rejalashtirilgan postlar hisobga olinadi)."""
    from apps.content.insights import best_common_slot
    r = best_common_slot(item.business, _item_platforms(item), exclude_item=item.pk)
    if r:
        item.scheduled_at = r["at"]
        item.save(update_fields=["scheduled_at", "updated_at"])
    return r


def _maybe_autotime(request, item, form) -> None:
    if form.cleaned_data.get("auto_time") and not item.scheduled_at and item.targets.exists():
        r = _apply_autotime(item)
        if r:
            messages.success(request, f"Vaqt avtomatik tanlandi: {r['label']} ({r['reason']}).")
        else:
            messages.warning(request, "Bo'sh qulay vaqt topilmadi — vaqtni qo'lda tanlang.")
    elif form.cleaned_data.get("auto_time") and not item.targets.exists():
        messages.warning(request, "Vaqtni avtomatik tanlash uchun avval platforma/akkauntni belgilang.")


@login_required
@require_POST
def content_autotime(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    if item.status in ("publishing", "published"):
        messages.error(request, "Bu post allaqachon nashr qilingan yoki qilinmoqda.")
        return redirect("content_detail", pk=item.pk)
    if not item.targets.exists():
        messages.error(request, "Avval platforma/akkauntni belgilang (Tahrirlash).")
        return redirect("content_detail", pk=item.pk)
    r = _apply_autotime(item)
    if not r:
        messages.warning(request, "Bo'sh qulay vaqt topilmadi.")
        return redirect("content_detail", pk=item.pk)
    audit("content.autotime", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title, "to": r["label"]})
    res = state.on_item_edited(item, request.user)
    messages.success(request, f"Eng yaxshi bo'sh vaqt tanlandi: {r['label']} — {r['reason']}." + ("" if res in ("", "scheduled") else f" Rejalashtirib bo'lmadi: {res}"))
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def content_autotime_many(request):
    """Vaqti belgilanmagan qoralamalarni ketma-ket eng yaxshi bo'sh vaqtlarga qo'yadi."""
    items = _items(request, "calendar.edit").filter(scheduled_at__isnull=True, status__in=["draft", "failed"]).order_by("created_at")[:30]
    ok = bad = 0
    for it in items:
        if not it.targets.exists():
            bad += 1
            continue
        r = _apply_autotime(it)
        if r:
            res = state.on_item_edited(it, request.user)
            audit("content.autotime", user=request.user, business_id=it.business_id, target=f"item:{it.pk}", detail={"title": it.title, "to": r["label"]})
            ok += 1
            if res not in ("", "scheduled"):
                bad += 1
        else:
            bad += 1
    messages.success(request, f"{ok} ta post eng yaxshi bo'sh vaqtlarga qo'yildi." + (f" {bad} tasi uchun vaqt qo'yib bo'lmadi (platforma belgilanmagan yoki qoida to'sqinlik qilmoqda)." if bad else ""))
    return redirect("calendar")


@login_required
def content_edit(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    platform = _item_platform(item)
    form = _form(request, item, request.POST or None, platform=platform)
    old_assignee = item.assignee_id
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.options = form.options_from_cleaned(item.options)
        item.save()
        _save_targets(item, form.cleaned_data["targets"])
        _save_uploads(request, item)
        _task_after_save(request, item, old_assignee)
        _maybe_autotime(request, item, form)
        audit("content.edit", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title})
        _after_save(request, item, "Saqlandi.")
        return redirect("content_detail", pk=item.pk)
    return _form_response(request, form, f"Tahrirlash: {item.title}", f"/kalendar/{item.pk}/", platform, item=item)


@login_required
def content_detail(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.view")
    base = f"/kalendar/{item.pk}"
    u = request.user
    acts = []
    for new, label, cls in (("scheduled", "Rejalashtirish", "primary"), ("draft", "Qoralamaga qaytarish", "")):
        if state.can_transition(item, new, u):
            acts.append({"t": label, "post": f"{base}/holat/{new}/", "cls": cls})
    if item.status in ("draft", "scheduled", "failed") and perms.can(u, "publish.publish", item.business):
        acts.append({"t": "Hozir nashr qilish", "post": f"{base}/hozir/", "cls": "blue", "confirm": "Post hoziroq nashr qilinadi. Davom etasizmi?"})
    if item.status in ("draft", "failed") and not item.scheduled_at and perms.can(u, "calendar.edit", item.business):
        acts.append({"t": "⚡ Eng yaxshi vaqtga qo'yish", "post": f"{base}/avto-vaqt/", "cls": "blue"})
    acts.append({"t": "Qoidalarni tekshirish", "post": f"{base}/tekshir/", "cls": ""})
    if item.status != "publishing" and perms.can(u, "calendar.delete", item.business):
        acts.append({"t": "O'chirish (savatga)", "post": f"{base}/ochir/", "cls": "danger",
                     "confirm": "Post savatga o'tadi (30 kun ichida tiklash mumkin)." + (" Platformada chiqqan post o'chmaydi." if item.status == "published" else "")})
    if item.targets.filter(status__in=["failed", "blocked"]).exists() and perms.can(u, "publish.publish", item.business):
        acts.append({"t": "Xatolarni qayta urinish", "post": f"{base}/qayta/", "cls": "primary"})
    probs = []
    seen_pl, seen_msg = set(), set()
    for rc in item.rule_checks.order_by("-checked_at")[:12]:
        if rc.platform in seen_pl:
            continue
        seen_pl.add(rc.platform)
        for p in rc.problems:
            msg = p.get("message_uz") or p.get("message", "")
            if (p.get("rule_id", ""), msg) in seen_msg:
                continue
            seen_msg.add((p.get("rule_id", ""), msg))
            probs.append({"platform": rc.platform, "status": rc.status, "rule": p.get("rule_id", ""), "msg": msg})
    targets = list(item.targets.select_related("account"))
    sel = {}
    for t in targets:
        sel.setdefault(t.account.platform, []).append({"name": t.account.name, "handle": t.account.handle})
    from apps.web.common import STATUS_CLASS
    ctx = {
        "item": item, "base": base, "acts": acts, "probs": probs, "targets": targets, "assets": list(item.assets.order_by("position", "id")),
        "status_cls": STATUS_CLASS.get(item.status, ""), "can_edit": perms.can(u, "calendar.edit", item.business),
        "scheduled_local": ui.dt(item.scheduled_at) if item.scheduled_at else "belgilanmagan",
        "rule_label": {"pass": "Muammo yo'q", "warn": "Ogohlantirish bor", "block": "Nashrga to'sqinlik bor"}.get(item.rule_status, "tekshirilmagan"),
        "rule_cls": {"pass": "ok", "warn": "warn", "block": "bad"}.get(item.rule_status, ""),
        "pv": {"text": item.text or "", "mt": item.media_type, "sel": sel, "media": _media_list(item), "ytTitle": (item.options or {}).get("title", ""),
               "first": next(iter(sel), "telegram"),
               "ratio": {"ig_4x5": 0.8, "ig_1x1": 1, "ig_191": 1.91, "v_9x16": 9 / 16, "h_16x9": 16 / 9}.get((item.options or {}).get("media_size", ""), 0),
               "fit": (item.options or {}).get("fit_mode", ""), "crop": (item.options or {}).get("crop") or {"x": .5, "y": .5, "z": 1},
               "size": (item.options or {}).get("media_size", "orig"), "buttons": [[b.get("text", "") for b in row] for row in ((item.options or {}).get("buttons") or [])]},
        "title": item.title or "Kontent", "asset_form": AssetForm(),
        "history": history_for_item(item) if perms.can(u, "calendar.view", item.business) else [],
    }
    tctx = _task_ctx(item, u)
    from apps.core.utils import fmt_dt
    return spa.respond(request, {
        "kind": "content_detail", "id": item.pk, "title": item.title or "(nomsiz)", "business": item.business.name, "text": item.text, "status": item.status,
        "status_label": item.get_status_display(), "status_cls": ctx["status_cls"], "format": item.get_media_type_display(), "type": item.media_type,
        "scheduled": ctx["scheduled_local"], "rule_label": ctx["rule_label"], "rule_cls": ctx["rule_cls"], "acts": [{"label": a["t"], "post": a["post"], "cls": a.get("cls", ""), "confirm": a.get("confirm")} for a in acts],
        "can_edit": ctx["can_edit"], "can_create": tctx["can_create"], "can_comment": tctx["can_comment"], "pv": ctx["pv"], "probs": probs,
        "info": {"author": str(item.created_by) if item.created_by else "—", "assignee": str(item.assignee) if item.assignee else "—", "goal": item.goal, "hook": item.hook_idea, "cta": item.cta, "notes": item.notes, "brief": item.brief},
        "targets": [{"account": str(t.account), "platform": t.account.platform, "status": t.status, "status_label": t.get_status_display(), "published_at": ui.dt(t.published_at) if t.published_at else "",
                     "url": t.url, "error": t.error} for t in targets],
        "assets": [{"id": a.pk, "kind": a.kind, "name": a.original_name, "size": a.size, "url": f"{base}/media/{a.pk}/"} for a in ctx["assets"]],
        "task": {**{k: v for k, v in tctx["task"].items() if k != "steps"}, "steps": [{"key": x[0], "label": x[1], "cls": x[2]} for x in tctx["task"]["steps"]]},
        "staff": [{"id": x.pk, "name": x.get_full_name() or x.username} for x in tctx["staff"]],
        "comments": [{"user": (c.user.get_full_name() or c.user.username) if c.user else "tizim", "at": fmt_dt(c.created_at), "text": c.text, "kind": c.kind} for c in tctx["comments"]],
        "results": _results_ctx(item, u), "posts": _posts_ctx(item, u), "history": ctx["history"], "ai_draft": bool(item.ai_draft and not item.ai_draft_reviewed),
        "due_local": tctx["task"]["due_local"], "brief": item.brief})


def _posts_ctx(item, u) -> list:
    """Nashr qilingan postlar (statistika sahifasiga havola uchun)."""
    if not perms.can(u, "analytics.view", item.business):
        return []
    return [{"id": p.pk, "platform": p.platform} for p in item.posts.all().order_by("-id")[:10]]


def _results_ctx(item, u) -> list:
    if not perms.can(u, "analytics.view", item.business):
        return []
    from apps.studio.models import PostInsight
    out = []
    for ins in PostInsight.objects.filter(post__content_item=item).select_related("post").order_by("-created_at")[:6]:
        w = (ins.numbers or {}).get("summary_window")
        out.append({"win": {"24h": "24 soat", "7d": "7 kun"}.get(w, "tahlil"), "plat": ins.post.platform.title(), "text": ins.text, "verdict": ins.verdict,
                    "at": ui.dt(ins.created_at), "url": ins.post.url})
    return out


def _task_ctx(item, u) -> dict:
    from apps.accounts.models import User
    from apps.content import workflow
    can_edit = perms.can(u, "calendar.edit", item.business)
    staff = [x for x in User.objects.filter(is_active=True).order_by("first_name", "username") if x.is_admin or perms.has_business(x, item.business_id)] if can_edit else []
    ds = item.design_status
    steps = []
    if can_edit and ds in ("todo", "revision"):
        steps.append(("doing", "▶ Boshladim", "blue"))
    if can_edit and ds in ("todo", "doing", "revision"):
        steps.append(("accepted", "✅ Bajarildi", "primary"))
    due_local = item.due_at.astimezone(__import__("apps.core.utils", fromlist=["tz"]).tz()).strftime("%Y-%m-%dT%H:%M") if item.due_at else ""
    late = bool(item.due_at and item.due_at < timezone.now() and ds in workflow.OPEN)
    return {"task": {"status": ds, "label": workflow.DESIGN_STATUS.get(ds, ""), "cls": workflow.DESIGN_CLASS.get(ds, ""), "steps": steps, "late": late,
                     "due_local": due_local, "due_text": ui.dt(item.due_at) if item.due_at else "", "can_assign": can_edit},
            "staff": staff, "comments": list(item.comments.select_related("user")[:200]), "can_comment": perms.can(u, "calendar.view", item.business),
            "can_create": perms.can(u, "calendar.create", item.business)}


@login_required
def content_media(request, pk, aid):
    """Himoyalangan media: faqat shu kontentga kirish huquqi bor foydalanuvchiga (Range qo'llab-quvvatlanadi)."""
    import mimetypes
    import os
    import re

    from django.http import FileResponse, Http404, HttpResponse
    item = get_obj(request, ContentItem, pk, "calendar.view")
    a = item.assets.filter(pk=aid).first()
    if not a:
        raise Http404
    path = a.file.path
    if not os.path.exists(path):
        raise Http404
    ctype = mimetypes.guess_type(a.original_name or path)[0] or "application/octet-stream"
    size = os.path.getsize(path)
    rng = request.headers.get("Range", "")
    m = re.match(r"bytes=(\d*)-(\d*)", rng)
    if m and (m.group(1) or m.group(2)):
        start = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2)))
        end = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end:
            return HttpResponse(status=416)
        with open(path, "rb") as f:
            f.seek(start)
            data = f.read(end - start + 1)
        r = HttpResponse(data, status=206, content_type=ctype)
        r["Content-Range"] = f"bytes {start}-{end}/{size}"
    else:
        r = FileResponse(open(path, "rb"), content_type=ctype)
    r["Accept-Ranges"] = "bytes"
    r["Content-Length"] = str(r.get("Content-Length") or size)
    r["Cache-Control"] = "private, max-age=300"
    return r


@login_required
@require_POST
def content_now(request, pk):
    """Hoziroq nashr: vaqtni hozirdan 1 daqiqa keyinga qo'yib rejalashtiradi."""
    item = get_obj(request, ContentItem, pk, "publish.publish")
    item.scheduled_at = timezone.now() + timedelta(minutes=1)
    item.save(update_fields=["scheduled_at"])
    if item.status == "scheduled":
        messages.success(request, "Post 1 daqiqa ichida nashr qilinadi.")
    else:
        res = state.auto_schedule(item, request.user)
        messages.success(request, "Post 1 daqiqa ichida nashr qilinadi.") if res == "scheduled" else messages.error(request, f"Rejalashtirib bo'lmadi: {res or 'maqsad (platforma) tanlanmagan'}")
    audit("content.publish_now", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title})
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def content_transition(request, pk, new):
    item = get_obj(request, ContentItem, pk, "calendar.view")
    try:
        state.transition(item, new, request.user)
        messages.success(request, f"Holat: {item.get_status_display()}")
    except csvc.NotReady as e:
        messages.error(request, str(e) + " " + "; ".join(p.get("message_uz", "") for pl in (e.problems or {}).values() for p in pl.get("problems", [])) if isinstance(e.problems, dict) else str(e))
    except (state.InvalidTransition, state.NotAllowed) as e:
        messages.error(request, str(e))
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def content_check(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.view")
    r = csvc.check_item(item)
    messages.info(request, f"Qoidalar natijasi: {r['status']}")
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def content_override(request, pk):
    item = get_obj(request, ContentItem, pk, "publish.publish")
    try:
        csvc.override_warnings(item, request.user, request.POST.get("reason", ""))
        messages.success(request, "Ogohlantirish asoslab o'tkazildi (jurnalga yozildi).")
    except (PermissionError, ValueError) as e:
        messages.error(request, str(e))
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def content_retry(request, pk):
    item = get_obj(request, ContentItem, pk, "publish.publish")
    n = csvc.retry_failed(item, request.user)
    messages.success(request, f"{n} ta maqsad qayta urinishga qo'yildi.")
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def content_ai_reviewed(request, pk):
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    item.ai_draft_reviewed = True
    item.save(update_fields=["ai_draft_reviewed"])
    audit("content.ai_reviewed", user=request.user, business_id=item.business_id, target=f"item:{item.pk}")
    return redirect("content_detail", pk=item.pk)


def _next_pos(item) -> int:
    from django.db.models import Max
    m = item.assets.aggregate(m=Max("position"))["m"]
    return 0 if m is None else m + 1


def _task_after_save(request, item, old_assignee) -> None:
    """Formada mas'ul/muddat/topshiriq berilgan bo'lsa vazifa ochiladi va xodimga xabar boradi."""
    from apps.content import workflow
    if item.assignee_id and (item.assignee_id != old_assignee or not item.design_status):
        item.design_status = "todo"
        item.save(update_fields=["design_status"])
        workflow.add_comment(item, request.user, f"Vazifa berildi — mas'ul: {workflow.name_of(item.assignee)}" + (f", muddat: {ui.dt(item.due_at)}" if item.due_at else ""), kind="status")
        if item.assignee_id != request.user.pk:
            from apps.core.notify import notify
            notify("task.assigned", f"Yangi vazifa: {item.title or 'post'}", (item.brief[:300] or "Postga fayl tayyorlash kerak.") + (f"\nMuddat: {ui.dt(item.due_at)}" if item.due_at else ""),
                   business_id=item.business_id, link=f"/kalendar/{item.pk}/", users=[item.assignee])
    elif not item.assignee_id and item.design_status:
        item.design_status = ""
        item.save(update_fields=["design_status"])


def _save_uploads(request, item) -> None:
    """Forma ichidan yuklangan media fayllar (rasm/video)."""
    ok = 0
    for f in request.FILES.getlist("files"):
        ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
        if ext not in ALLOWED_EXT or ALLOWED_EXT[ext] == "audio":
            messages.warning(request, f"«{f.name}» yuklanmadi. Ruxsat etilgan: jpg, png, webp, mp4, mov.")
            continue
        h = hashlib.sha256()
        for ch in f.chunks():
            h.update(ch)
        f.seek(0)
        asset = ContentAsset.objects.create(item=item, file=f, kind=ALLOWED_EXT[ext], original_name=f.name[:200], size=f.size, sha256=h.hexdigest(), position=_next_pos(item))
        _queue_cloud(asset)
        ok += 1
    for cid in request.POST.getlist("cloud_ids"):
        if cid.isdigit() and _attach_cloud(request, item, int(cid)):
            ok += 1
    if ok:
        messages.success(request, f"{ok} ta media fayl biriktirildi.")
        audit("content.media", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"count": ok, "title": item.title})


def _attach_cloud(request, item, tid: int) -> bool:
    """Cloudflare'da turgan faylni postga biriktiradi (mahalliy nusxa olinadi: kesish va tekshiruv uchun)."""
    import os
    import requests
    from django.core.files.base import ContentFile
    from apps.content import temphost
    from apps.content.models import TempObject
    o = TempObject.objects.filter(pk=tid, status="uploaded").first()
    if o is None or (o.business_id or (o.item.business_id if o.item_id else None)) != item.business_id:
        messages.warning(request, "Cloudflare fayli topilmadi yoki boshqa biznesga tegishli.")
        return False
    name = (o.filename or o.key)[:150]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXT or ALLOWED_EXT[ext] == "audio":
        messages.warning(request, f"«{name}» turi qo'llab-quvvatlanmaydi.")
        return False
    data = None
    if o.asset_id and o.asset.file and os.path.exists(o.asset.file.path):
        with open(o.asset.file.path, "rb") as fh:
            data = fh.read()
    else:
        try:
            r = requests.get(temphost.view_url(o), timeout=300)
            r.raise_for_status()
            data = r.content
        except Exception:  # noqa: BLE001
            messages.warning(request, f"«{name}» ni Cloudflare'dan olib bo'lmadi. Qayta urinib ko'ring.")
            return False
    asset = ContentAsset(item=item, kind=ALLOWED_EXT[ext], original_name=name, size=len(data), sha256=hashlib.sha256(data).hexdigest(), cloud=o, position=_next_pos(item))
    asset.file.save(name, ContentFile(data), save=True)
    return True


def _queue_cloud(asset) -> None:
    """Media Cloudflare'ga ham yuklanadi (navbatda); holati «Cloudflare» menyusida."""
    from django.conf import settings as dj
    from apps.jobs.queue import enqueue
    from apps.content import temphost
    if asset.kind not in ("image", "video"):
        return
    try:
        o = temphost.register_pending(asset, fake=dj.USE_FAKES)
        if o:
            enqueue("cloud_upload", {"temp_id": o.pk}, queue="media", business_id=asset.item.business_id, dedupe_key=f"cu:{o.pk}")
    except Exception:  # noqa: BLE001 — Cloudflare muammosi post saqlanishiga halal bermasin
        pass


ALLOWED_EXT = {"jpg": "image", "jpeg": "image", "png": "image", "webp": "image", "mp4": "video", "mov": "video", "mp3": "audio"}


@login_required
@require_POST
def content_asset(request, pk):
    """Postga bir yo'la bir nechta fayl (kompyuterdan yoki Cloudflare'dan) qo'shish."""
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    if not request.FILES.getlist("files") and not request.POST.getlist("cloud_ids"):
        messages.error(request, "Fayl tanlanmadi.")
        return redirect("content_detail", pk=item.pk)
    _save_uploads(request, item)
    state.on_item_edited(item, request.user)
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def content_asset_delete(request, pk, aid):
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    a = get_object_or_404(item.assets, pk=aid)
    name = a.original_name
    if item.status == "publishing":
        messages.error(request, "Nashr jarayonida fayl o'chirilmaydi.")
        return redirect("content_detail", pk=item.pk)
    a.delete()   # Cloudflare'dagi nusxa qoladi (faqat qo'lda o'chiriladi)
    audit("content.media_delete", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"file": name[:80]})
    state.on_item_edited(item, request.user)
    messages.success(request, f"«{name}» postdan olib tashlandi (Cloudflare'dagi nusxa saqlanadi).")
    return redirect("content_detail", pk=item.pk)


@login_required
@require_POST
def content_asset_replace(request, pk, aid):
    """Tahrirlangan (kesilgan/siljitilgan) rasm bilan almashtirish."""
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    a = get_object_or_404(item.assets, pk=aid)
    f = request.FILES.get("file")
    if not f or a.kind != "image" or f.name.rsplit(".", 1)[-1].lower() not in ("jpg", "jpeg", "png", "webp"):
        messages.error(request, "Faqat rasmni almashtirish mumkin (jpg, png, webp).")
        return redirect("content_detail", pk=item.pk)
    h = hashlib.sha256()
    for ch in f.chunks():
        h.update(ch)
    f.seek(0)
    a.file.save(f.name, f, save=False)
    a.size, a.sha256, a.cloud = f.size, h.hexdigest(), None
    a.save()
    _queue_cloud(a)
    audit("content.media_edit", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"file": a.original_name[:80]})
    state.on_item_edited(item, request.user)
    messages.success(request, "Rasm yangilandi.")
    return redirect("content_detail", pk=item.pk)


@login_required
@require_permission("publish.view")
def publish_log(request):
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "publish.view").values_list("pk", flat=True))
    qs = PublishAttempt.objects.filter(target__item__business_id__in=ids).select_related("target__item", "target__account").order_by("-started_at")
    page = Paginator(qs, 40).get_page(request.GET.get("p"))
    rows = [[ui.dt(a.started_at), ui.link(a.target.item.title, f"/kalendar/{a.target.item_id}/"), str(a.target.account), f"#{a.number}",
             ui.badge(a.status, {"success": "ok", "failed": "failed"}.get(a.status, "pending")), (a.error or "")[:140] or "—"] for a in page]
    return ui.page(request, "Nashr jurnali", [ui.table(None, ["Vaqt", "Kontent", "Hisob", "Urinish", "Natija", "Xato"], rows, "Hali nashr urinishi bo'lmagan.")])


PLAT_NAMES = {"telegram": "Telegram", "instagram": "Instagram", "youtube": "YouTube"}
FMT_NAMES = {"text": "Matn", "image": "Rasm", "video": "Video", "album": "Albom", "carousel": "Karusel", "reel": "Reels", "short": "Shorts", "story": "Stories"}


@login_required
@require_permission("analytics.view")
def analytics(request):
    from collections import defaultdict
    from apps.metrics.models import Story
    b = request.business
    if not b:
        messages.info(request, "Tahlil uchun biznesni tanlang.")
        return redirect("dashboard")
    days = int(request.GET.get("days", 30)) if request.GET.get("days", "30").isdigit() else 30
    accs = list(SocialAccount.objects.filter(business=b, archived_at__isnull=True))
    plats = [p for p in PLAT_NAMES if any(a.platform == p for a in accs)]
    if not plats:
        return ui.page(request, "Tahlil", [{"type": "text", "title": "Ulanish yo'q", "text": "Avval Ulanishlar bo'limida Telegram, Instagram yoki YouTube ni ulang."}], subtitle=b.name)
    plat = request.GET.get("p") if request.GET.get("p") in plats else plats[0]
    fmt = request.GET.get("f", "")
    pacc = [a for a in accs if a.platform == plat]
    ids = [a.pk for a in pacc]
    nposts = {p: Post.objects.filter(business=b, platform=p).count() for p in plats}
    blocks = [ui.tabs([(f"{PLAT_NAMES[p]} ({nposts[p]})", f"?p={p}&days={days}", p == plat) for p in plats]),
              ui.tabs([(f"{d} kun", f"?p={plat}&days={d}", days == d) for d in (7, 30, 90)])]
    c = an.compare_periods(b, days, ids)
    k, dp = c["current"], c["delta_pct"]
    pct = lambda key: (f" ({dp[key]:+.0f}%)" if dp.get(key) is not None else "")
    er = f"{k['er'] * 100:.2f}%" if k.get("er") is not None else "—"
    blocks.append(ui.kv(f"{PLAT_NAMES[plat]} · oxirgi {days} kun", [
        ("Obunachi", f"{k.get('followers')}{pct('followers')}"), ("Postlar", f"{k.get('posts')}{pct('posts')}"), ("Ko'rishlar", f"{k.get('views')}{pct('views')}"),
        ("O'rtacha ER", er), ("Layklar", k.get("likes")), ("Izohlar", k.get("comments")), ("Ulashishlar", k.get("shares")), ("Saqlashlar", k.get("saves"))]))
    if (k.get("posts") or 0) < 5:
        blocks.append({"type": "text", "title": "Ma'lumot kam", "text": f"{PLAT_NAMES[plat]} bo'yicha so'nggi {days} kunda atigi {k.get('posts') or 0} ta post statistikasi bor. "
                                                                         "Natijalar taxminiy; AI tavsiyalar shu platforma uchun umumiy SMM qoidalariga ham tayanadi. Kunlar sonini 90 ga oshirib ko'ring."})
    charts = []
    tot = defaultdict(int)
    for a in pacc:
        for pnt in an.follower_series(a, days):
            tot[pnt["date"]] += pnt["followers"] or 0
    if len(tot) > 1:
        ds = sorted(tot)
        charts.append({"id": "an1", "kind": "line", "labels": [d[5:] for d in ds], "series": [{"name": "Obunachi", "data": [tot[d] for d in ds]}]})
        blocks.append({"type": "chart", "title": "Obunachilar dinamikasi", "id": "an1"})
    # --- formatlar bo'yicha ajratish ---
    ty = an.by_type(b, max(days, 60), platform=plat)
    rows = [[FMT_NAMES.get(t["type"], t["type"]), t["count"], int(t["avg_views"]), f"{(t['avg_er'] or 0) * 100:.2f}%",
             ui.link("Faqat shu format", f"?p={plat}&days={days}&f={t['type']}")] for t in ty]
    if plat == "instagram":
        st_rows = list(Story.objects.filter(account__in=pacc, published_at__gte=timezone.now() - timedelta(days=days)))
        if st_rows:
            views = []
            for stv in st_rows:
                h = stv.history.order_by("-taken_at").first()
                if h and h.views is not None:
                    views.append(h.views)
            rows.append(["Stories", len(st_rows), int(sum(views) / len(views)) if views else 0, "—", ""])
    blocks.append(ui.table("Format bo'yicha alohida natija", ["Format", "Postlar", "O'rtacha ko'rish", "O'rtacha ER", ""], rows, "Bu platformada hali statistika yo'q."))
    if ty:
        charts.append({"id": "an2", "kind": "bar", "labels": [FMT_NAMES.get(t["type"], t["type"]) for t in ty], "series": [{"name": "ER %", "data": [round((t["avg_er"] or 0) * 100, 2) for t in ty]}]})
        blocks.append({"type": "chart", "title": "Format bo'yicha ER %", "id": "an2"})
    ttl = f" ({FMT_NAMES.get(fmt, fmt)})" if fmt else ""
    top = an.top_posts(b, 10, days=max(days, 60), platform=plat, media_type=fmt or None)
    blocks.append(ui.table(f"Eng yaxshi postlar{ttl}", ["Post", "Format", "Ko'rish", "ER", ""],
                           [[(r.post.text or "")[:70], FMT_NAMES.get(r.post.media_type, r.post.media_type), r.views, f"{(r.er or 0) * 100:.2f}%", ui.link("Nega ishladi?", f"/tahlil/post/{r.post_id}/")] for r in top],
                           "Hali ER hisoblangan post yo'q."))
    bt = an.best_times(b, 90, platform=plat, media_type=fmt or None)
    wd = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
    blocks.append(ui.table(f"Eng yaxshi kunlar{ttl}", ["Hafta kuni", "O'rtacha ER", "Postlar"], [[wd[d], f"{e * 100:.2f}%", n] for d, e, n in bt["weekday"][:7]], "Yetarli ma'lumot yo'q."))
    blocks.append(ui.table(f"Eng yaxshi soatlar{ttl}", ["Soat", "O'rtacha ER", "Postlar"], [[f"{h:02d}:00", f"{e * 100:.2f}%", n] for h, e, n in bt["hour"][:6]], "Yetarli ma'lumot yo'q."))
    blocks.append(ui.table("Hashtag", ["Hashtag", "Ishlatilgan", "O'rtacha ER"], [[h["tag"], h["count"], f"{h['avg_er'] * 100:.2f}%"] for h in an.hashtag_stats(b, platform=plat)], "Takrorlangan hashtag yo'q."))
    return ui.page(request, "Tahlil", blocks, subtitle=f"{b.name} · {PLAT_NAMES[plat]}", charts=charts)


@login_required
@require_permission("analytics.view")
def post_list(request):
    """Barcha postlar statistikasi: platforma / ulanish / format bo'yicha saralash va tartiblash."""
    from apps.metrics.analytics import latest_metrics_qs
    b = request.business
    if not b:
        return spa.respond(request, {"kind": "need_business", "title": "Postlar statistikasi"})
    accs = list(SocialAccount.objects.filter(business=b, archived_at__isnull=True))
    f = {"account": request.GET.get("account", ""), "format": request.GET.get("format", ""), "sort": request.GET.get("sort", "date")}
    qs = latest_metrics_qs(b.pk)
    if f["account"].isdigit():
        qs = qs.filter(post__account_id=int(f["account"]))
    if f["format"]:
        qs = qs.filter(post__media_type=f["format"])
    order = {"date": "-post__published_at", "views": "-views", "er": "-er", "likes": "-likes"}.get(f["sort"], "-post__published_at")
    page = Paginator(qs.select_related("post__account").order_by(order, "-pk"), 25).get_page(request.GET.get("p"))
    return spa.respond(request, {
        "kind": "post_list", "pager": spa.pager_json(page), "f": f, "accounts": [{"id": a.pk, "name": str(a)} for a in accs],
        "formats": [[k, v] for k, v in FMT_NAMES.items()],
        "rows": [{"id": r.post_id, "text": (r.post.text or "")[:120], "platform": r.post.platform, "account": r.post.account.name, "format": FMT_NAMES.get(r.post.media_type, r.post.media_type),
                  "date": ui.dt(r.post.published_at), "views": r.views, "likes": r.likes, "comments": r.comments, "shares": r.shares, "saves": r.saves, "er": r.er, "url": r.post.url}
                 for r in page.object_list]})


@login_required
def post_insight(request, pk):
    """Bitta post: raqamlar, dinamika (vaqt bo'yicha), biznes o'rtachasi bilan solishtirish va AI tahlil («Nega ishladi?»)."""
    post = get_obj(request, Post, pk, "analytics.view")
    from apps.studio.models import PostInsight
    from apps.studio.services import why_worked
    if request.method == "POST":
        if not perms.can(request.user, "ai_studio.create", post.business):
            raise PermissionDenied
        try:
            why_worked(post, request.user)
            messages.success(request, "AI tahlil tayyor.")
        except Exception as e:  # noqa: BLE001
            messages.error(request, getattr(e, "user_message_uz", None) or f"AI xatosi: {e}")
        return redirect("post_insight", pk=post.pk)
    ins = PostInsight.objects.filter(post=post).order_by("-created_at").first()
    nums = an.numeric_basis(post)
    last = post.history.order_by("-taken_at").first()
    base = an.median_baseline(post.business)
    hist = [{"at": ui.dt(h.taken_at), "age_h": round(h.age_hours or 0, 1), "views": h.views, "likes": h.likes, "comments": h.comments, "er": h.er}
            for h in post.history.order_by("taken_at")[:60]]
    d = (ins.data or {}) if ins else {}
    return spa.respond(request, {
        "kind": "post_insight", "id": post.pk, "text": post.text or "", "platform": post.platform, "account": post.account.name, "format": FMT_NAMES.get(post.media_type, post.media_type),
        "published": ui.dt(post.published_at), "url": post.url, "item_id": post.content_item_id, "hashtags": post.hashtags or [],
        "now": {"views": last.views, "reach": last.reach, "likes": last.likes, "comments": last.comments, "shares": last.shares, "saves": last.saves, "er": last.er} if last else None,
        "baseline": {"er": base["er"], "views": base["views"], "n": base["n"]}, "ratio": {"er": nums.get("er_nisbati"), "views": nums.get("views_nisbati")},
        "winner": bool(last and an.is_winner(last, base)), "history": hist,
        "insight": {"verdict": ins.verdict, "summary": ins.text, "reasons": d.get("reasons") or [], "repeat": d.get("repeat") or [], "change": d.get("change") or [], "at": ui.dt(ins.created_at)} if ins else None,
        "can_ai": bool(perms.can(request.user, "ai_studio.create", post.business))})


# ---------------- Forma yordamchilari: AI matn/ssenariy va muqobil vaqt (JSON) ----------------
def _json_err(e):
    return JsonResponse({"error": getattr(e, "user_message_uz", None) or f"Xato: {e}"})


@login_required
@require_POST
@require_permission("calendar.create")
def ai_text(request):
    if not request.business:
        return JsonResponse({"error": "Avval biznesni tanlang."})
    from apps.studio import services as ss
    try:
        d = ss.smart_caption(request.business, request.POST.get("platform", "telegram"), request.POST.get("media_type", "text"),
                             request.POST.get("topic", "").strip(), request.POST.get("current", ""), user=request.user)
    except Exception as e:  # noqa: BLE001
        return _json_err(e)
    audit("ai.text", user=request.user, business_id=request.business.pk, target="ai", detail={"platform": request.POST.get("platform", "")})
    v = [x for x in (d.get("variants") or []) if isinstance(x, str) and x.strip()]
    tags = " ".join(h if str(h).startswith("#") else f"#{h}" for h in (d.get("hashtags") or []))
    return JsonResponse({"variants": v, "hashtags": tags, "why": d.get("why", "")} if v else {"error": "AI bo'sh javob qaytardi, qayta urinib ko'ring."})


@login_required
@require_POST
@require_permission("calendar.create")
def ai_youtube(request):
    if not request.business:
        return JsonResponse({"error": "Avval biznesni tanlang."})
    from apps.studio import services as ss
    try:
        d = ss.smart_youtube(request.business, request.POST.get("media_type", "video"), request.POST.get("topic", "").strip(),
                             request.POST.get("text", ""), user=request.user)
    except Exception as e:  # noqa: BLE001
        return _json_err(e)
    audit("ai.youtube", user=request.user, business_id=request.business.pk, target="ai", detail={"platform": request.POST.get("platform", "")})
    if not d.get("title"):
        return JsonResponse({"error": "AI sarlavha qaytarmadi, qayta urinib ko'ring."})
    tags = d.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    return JsonResponse({"title": str(d["title"])[:100], "tags": ", ".join(str(t).lstrip("#") for t in tags if t)[:480], "why": d.get("why", ""),
                         "privacy": d.get("privacy") if d.get("privacy") in ("public", "unlisted", "private") else ""})


@login_required
@require_POST
@require_permission("calendar.create")
def ai_script(request):
    if not request.business:
        return JsonResponse({"error": "Avval biznesni tanlang."})
    from apps.studio import services as ss
    try:
        sc, text = ss.smart_script(request.business, request.POST.get("platform", "instagram"), request.POST.get("media_type", "reel"),
                                   request.POST.get("topic", "").strip(), user=request.user)
    except Exception as e:  # noqa: BLE001
        return _json_err(e)
    audit("ai.script", user=request.user, business_id=request.business.pk, target="ai", detail={"platform": request.POST.get("platform", "")})
    return JsonResponse({"text": text, "title": sc.title, "script_id": sc.pk} if text else {"error": "AI ssenariy qaytarmadi, qayta urinib ko'ring."})


@login_required
@require_permission("calendar.create")
def time_suggest(request):
    if not request.business:
        return JsonResponse({"error": "Avval biznesni tanlang."})
    from apps.content.insights import suggest_times
    out = {}
    for plat in [p for p in request.GET.get("platform", "").split(",") if p in ("telegram", "instagram", "youtube")]:
        out[plat] = suggest_times(request.business, plat, exclude_item=int(request.GET.get("item") or 0) or None)
    return JsonResponse({"slots": out} if out else {"error": "Avval platformani tanlang."})
