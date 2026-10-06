from __future__ import annotations

import hashlib
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
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
from . import ui
from .common import get_obj
from .forms import AssetForm, ContentForm


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
    scheduled = qs.filter(scheduled_at__date__gte=first, scheduled_at__date__lt=nxt).order_by("scheduled_at").prefetch_related("targets__account", "assets")
    scheduled = list(scheduled)
    unsched = qs.filter(scheduled_at__isnull=True).exclude(status="published")[:30]
    row = lambda i: [ui.dt(i.scheduled_at), ui.link(i.title or "(nomsiz)", f"/kalendar/{i.pk}/"), i.business.name, i.get_media_type_display(),
                     ui.badge(i.get_status_display(), i.status), (i.rule_status or "—"),
                     ui.btn("🗑", f"/kalendar/{i.pk}/ochir/", "sm danger", f"«{i.title}» savatga o'tkazilsinmi?") if i.status != "publishing" else ""]
    base = f"m={first:%Y-%m}"
    q = lambda **kw: "?" + "&".join(f"{k}={v}" for k, v in {"m": f"{first:%Y-%m}", "status": st, "p": pf, "f": ff, **kw}.items() if v)
    chips = "".join(f'<a class="pill" href="{q(status=k)}">{v}</a> ' for k, v in STATUSES if k not in ("pending_approval", "approved")) + f'<a class="pill" href="{q(status="")}">Hammasi</a>'
    plat_chips = "".join(f'<a class="pill" style="{"background:#2563eb;color:#fff" if pf == k else ""}" href="{q(p=k, f="")}">{v}</a> ' for k, v in (("telegram", "Telegram"), ("instagram", "Instagram"), ("youtube", "YouTube"))) + f'<a class="pill" href="{q(p="", f="")}">Barcha platforma</a>'
    fmts = {"telegram": ["text", "image", "video", "album"], "instagram": ["image", "carousel", "reel", "story"], "youtube": ["video", "short"]}.get(pf, [])
    names = {"text": "Matn", "image": "Rasm", "video": "Video", "album": "Albom", "carousel": "Karusel", "reel": "Reels", "story": "Stories", "short": "Shorts"}
    fmt_chips = "".join(f'<a class="pill" style="{"background:#0ea5e9;color:#fff" if ff == t else ""}" href="{q(f=t)}">{names[t]}</a> ' for t in fmts)
    grid = _month_grid(request, first, scheduled)
    prev_q, nxt_q = q(m=prev.strftime("%Y-%m")), q(m=nxt.strftime("%Y-%m"))
    fmt_row = '<div class="mt">' + fmt_chips + "</div>" if fmt_chips else ""
    head = ('<div class="row sb"><a class="btn sm" href="' + prev_q + '">‹ ' + prev.strftime("%m.%Y") + '</a><b>' + first.strftime("%m.%Y") + '</b><a class="btn sm" href="' + nxt_q + '">' + nxt.strftime("%m.%Y") + ' ›</a></div>'
            '<div class="mt">' + plat_chips + "</div>" + fmt_row + '<div class="mt">' + chips + "</div>")
    blocks = [{"type": "html", "html": head},
              {"type": "html", "html": grid},
              ui.table("Ro'yxat ko'rinishi", ["Vaqt", "Sarlavha", "Biznes", "Tur", "Holat", "Qoida", ""], [row(i) for i in scheduled], "Bu oyda reja yo'q."),
              {"type": "actions", "title": "Vaqti belgilanmagan qoralamalar", "buttons": [ui.btn("⚡ Hammasini eng yaxshi bo'sh vaqtlarga qo'yish", "/kalendar/avto-vaqt/", "primary",
                                                                                             "Vaqti yo'q qoralamalar statistika asosida eng yaxshi bo'sh vaqtlarga rejalashtiriladi. Davom etasizmi?")] if unsched and request.business else []},
              ui.table(None, ["Vaqt", "Sarlavha", "Biznes", "Tur", "Holat", "Qoida", ""], [row(i) for i in unsched])]
    tb = [{"label": "Yangi kontent", "url": "/kalendar/yangi/", "cls": "primary"}] if request.business else []
    return ui.page(request, "Kontent kalendar", blocks, toolbar=tb)


PLAT_ICON = {"telegram": "TG", "instagram": "IG", "youtube": "YT"}
STATUS_COLOR = {"draft": "#94a3b8", "scheduled": "#3b82f6", "publishing": "#f59e0b", "published": "#22c55e", "failed": "#ef4444"}
WEEKDAYS = ["Du", "Se", "Chor", "Pay", "Ju", "Sha", "Yak"]


def _month_grid(request, first, items) -> str:
    """Oylik vizual setka: har kunda rangli post kartochkalari, bo'sh kunda «+»."""
    from calendar import monthcalendar
    from html import escape
    from apps.core.utils import tz as _tz
    by_day = {}
    for i in items:
        by_day.setdefault(i.scheduled_at.astimezone(_tz()).date(), []).append(i)
    today = timezone.localdate()
    can_create = bool(request.business)
    can_move = bool(request.business) and perms.can(request.user, "calendar.edit", request.business)
    import json as _json
    day_data = {}
    for d0, lst in by_day.items():
        arr = []
        for i in lst:
            th = next((a.pk for a in i.assets.all() if a.kind == "image"), None)
            arr.append({"id": i.pk, "t": i.scheduled_at.astimezone(_tz()).strftime("%H:%M"), "title": i.title or "(nomsiz)", "st": i.status, "stl": i.get_status_display(),
                        "c": STATUS_COLOR.get(i.status, "#64748b"), "fmt": i.get_media_type_display(), "pl": sorted({PLAT_ICON.get(t.account.platform, "?") for t in i.targets.all()}),
                        "rule": i.rule_status or "", "th": f"/kalendar/{i.pk}/media/{th}/" if th else ""})
        day_data[d0.isoformat()] = arr
    css = ("<style>.cg{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;margin-top:12px}"
           ".cg .h{font-weight:600;text-align:center;color:var(--muted,#64748b);font-size:12px}"
           ".cg .d{min-height:104px;border:1px solid var(--line,#e2e8f0);border-radius:10px;padding:5px;background:var(--card,#fff);position:relative;overflow:hidden}"
           ".cg .d.o{opacity:.4}.cg .d.t{border:2px solid #3b82f6}"
           ".cg .n{font-size:12px;font-weight:600;display:flex;justify-content:space-between}"
           ".cg .n a{color:var(--muted,#94a3b8);text-decoration:none;font-size:15px;line-height:1}"
           ".cg .p{display:block;margin-top:3px;padding:3px 5px;border-radius:6px;font-size:11px;color:#fff;text-decoration:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"
           ".cg .m{font-size:11px;color:var(--muted,#64748b);margin-top:2px}"
           ".cl{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px;font-size:12px}.cl i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px}"
           ".cg .d{cursor:pointer;transition:box-shadow .15s}.cg .d:hover{box-shadow:0 2px 10px rgba(0,0,0,.12)}.cg .d.sel{outline:3px solid var(--brand,#e11d2e)}"
           ".dw-scrim{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:80;display:none}.dw-scrim.on{display:block}"
           ".dw{position:fixed;top:0;right:0;bottom:0;width:min(420px,100%);background:var(--surface,#fff);z-index:81;box-shadow:-8px 0 30px rgba(0,0,0,.2);transform:translateX(105%);transition:transform .22s;display:flex;flex-direction:column}"
           ".dw.on{transform:none}.dw-h{padding:16px 18px;border-bottom:1px solid var(--border,#e2e8f0);display:flex;justify-content:space-between;align-items:center;gap:10px}"
           ".dw-b{padding:12px 14px;overflow:auto;flex:1;display:grid;gap:10px;align-content:start}"
           ".dw-i{display:flex;gap:10px;padding:10px;border:1px solid var(--border,#e2e8f0);border-radius:12px;color:inherit;text-decoration:none;background:var(--surface,#fff)}.dw-i:hover{border-color:var(--brand,#e11d2e)}"
           ".dw-i .th{width:56px;height:56px;border-radius:8px;object-fit:cover;background:var(--surface-2,#f1f5f9);flex:none}.dw-i .tt{font-weight:600;font-size:14px;line-height:1.3}.dw-i .mm{font-size:12px;color:var(--muted,#64748b);margin-top:3px}"
           ".dw-i .bd{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;color:#fff}"
           ".dw-f{padding:12px 14px;border-top:1px solid var(--border,#e2e8f0)}"
           ".cg .p[draggable=true]{cursor:grab}.cg .p.dragging{opacity:.4}.cg .d.over{outline:3px dashed var(--brand,#e11d2e);background:color-mix(in srgb,var(--brand,#e11d2e) 8%,transparent)}"
           ".dd-toast{position:fixed;left:50%;bottom:90px;transform:translateX(-50%);background:#0f172a;color:#fff;padding:10px 16px;border-radius:10px;z-index:99;font-size:14px;max-width:90%}.dd-toast.bad{background:#b91c1c}"
           ".cg .wd{display:none;color:var(--muted,#64748b);font-weight:500;margin-left:6px}"
           "@media(max-width:700px){.cg{grid-template-columns:1fr}.cg .h{display:none}.cg .d.e:not(.t){display:none}.cg .d{min-height:0;padding:8px}.cg .wd{display:inline}.cg .p{font-size:13px;padding:7px 9px}}</style>")
    cells = "".join(f'<div class="h">{w}</div>' for w in WEEKDAYS)
    for week in monthcalendar(first.year, first.month):
        for dn in week:
            if not dn:
                cells += '<div class="d o e"></div>'
                continue
            d = date(first.year, first.month, dn)
            its = by_day.get(d, [])
            plus = f'<a href="/kalendar/yangi/?date={d:%Y-%m-%d}" title="Shu kunga post qo\'shish">+</a>' if can_create else ""
            chips = ""
            for i in its[:4]:
                plats = "/".join(sorted({PLAT_ICON.get(t.account.platform, "?") for t in i.targets.all()})) or "—"
                title = escape((i.title or "(nomsiz)")[:28])
                drag = f' draggable="true" data-id="{i.pk}"' if can_move and i.status not in ("published", "publishing") else ""
                chips += (f'<a class="p" style="background:{STATUS_COLOR.get(i.status, "#64748b")}"{drag} href="/kalendar/{i.pk}/" '
                          f'title="{escape(i.title or "")} · {escape(i.get_status_display())}">{i.scheduled_at.astimezone(_tz()):%H:%M} {plats} {title}</a>')
            if len(its) > 4:
                chips += f'<div class="m">+ yana {len(its) - 4} ta</div>'
            cls = "d" + (" t" if d == today else "") + ("" if its else " e")
            cells += f'<div class="{cls}" data-day="{d:%Y-%m-%d}" tabindex="0" role="button"><div class="n"><span>{dn}<span class="wd">{WEEKDAYS[d.weekday()]}</span></span>{plus}</div>{chips}</div>'
    legend = "".join(f'<span><i style="background:{c}"></i>{escape(dict(STATUSES).get(k, k))}</span>' for k, c in STATUS_COLOR.items())
    drawer = ('<div class="dw-scrim" id="dwScrim"></div><aside class="dw" id="dw" aria-hidden="true"><div class="dw-h"><div><b id="dwTitle"></b><div class="muted" id="dwSub" style="font-size:13px"></div></div>'
              '<button type="button" class="btn sm" id="dwClose">✕</button></div><div class="dw-b" id="dwBody"></div>'
              + ('<div class="dw-f"><a class="btn primary" id="dwAdd" href="#">+ Shu kunga post qo\'shish</a></div>' if can_create else "") + "</aside>")
    js = ('<script type="application/json" id="calData">' + _json.dumps(day_data).replace("</", "<\\/") + '</script><script src="/static/js/cal_drawer.js"></script>')
    return f'{css}<div class="cg">{cells}</div><div class="cl">{legend}</div>{drawer}{js}'


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
              {"type": "text", "title": "Eslatma", "text": "Savatdagi postlar 30 kundan keyin avtomatik butunlay o'chadi. Tiklangan post qoralama holatida qaytadi. Cloudflare'dagi fayllar alohida: «Cloudflare» menyusidan o'chiriladi."}]
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
        return render(request, "content_choose.html", {"title": "Yangi kontent", "cards": cards})
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
    return render(request, "content_form.html", {"title": title, "form": form, "back": "/kalendar/yangi/" if platform else "/kalendar/", "acc_map": _acc_map(form),
                                                 "targets_ctx": _targets_ctx(form), "existing_media": _media_list(form.instance), "tpl_list": _tpl_list(request, platform), **_plat_ctx(request, platform)})


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
    return render(request, "content_form.html", {"title": f"Tahrirlash: {item.title}", "form": form, "back": f"/kalendar/{item.pk}/", "acc_map": _acc_map(form), "targets_ctx": _targets_ctx(form), "existing_media": _media_list(form.instance), **_plat_ctx(request, platform, item)})


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
    if perms.can(u, "calendar.edit", item.business):
        acts.append({"t": "✅ Tayyor, ko'rib chiqing", "post": f"{base}/tayyor/", "cls": "", "confirm": "Mas'ul/SMM mutaxassisga «tayyor» bildirishnomasi yuboriladi."})
    if item.status in ("draft", "failed") and not item.scheduled_at and perms.can(u, "calendar.edit", item.business):
        acts.append({"t": "⚡ Eng yaxshi vaqtga qo'yish", "post": f"{base}/avto-vaqt/", "cls": "blue"})
    acts.append({"t": "Qoidalarni tekshirish", "post": f"{base}/tekshir/", "cls": ""})
    if item.status != "publishing" and perms.can(u, "calendar.delete", item.business):
        acts.append({"t": "O'chirish (savatga)", "post": f"{base}/ochir/", "cls": "danger",
                     "confirm": "Post savatga o'tadi (30 kun ichida tiklash mumkin)." + (" Platformada chiqqan post o'chmaydi." if item.status == "published" else "")})
    if item.targets.filter(status__in=["failed", "blocked"]).exists() and perms.can(u, "publish.publish", item.business):
        acts.append({"t": "Xatolarni qayta urinish", "post": f"{base}/qayta/", "cls": "primary"})
    probs = []
    for rc in item.rule_checks.order_by("-checked_at")[:3]:
        for p in rc.problems:
            probs.append({"platform": rc.platform, "status": rc.status, "rule": p.get("rule_id", ""), "msg": p.get("message_uz") or p.get("message", "")})
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
    ctx.update(_task_ctx(item, u))
    ctx["results"] = _results_ctx(item, u)
    return render(request, "content_detail.html", ctx)


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
    can_review = perms.can(u, "calendar.create", item.business) or u.is_admin
    staff = [x for x in User.objects.filter(is_active=True).order_by("first_name", "username") if x.is_admin or perms.has_business(x, item.business_id)] if can_edit else []
    ds = item.design_status
    steps = []
    if can_edit and ds in ("todo", "revision"):
        steps.append(("doing", "▶ Boshladim", "blue"))
    if can_edit and ds in ("todo", "doing", "revision"):
        steps.append(("ready", "✅ Tayyor, ko'rib chiqing", "primary"))
    if can_review and ds == "ready":
        steps += [("accepted", "👍 Qabul qilish", "primary"), ("revision", "↩ Qayta ko'rib chiqing", "danger")]
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


def _csrf(request):
    from django.middleware.csrf import get_token
    return get_token(request)


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
@require_POST
def content_ready(request, pk):
    """Dizayner «tayyor» deb belgilaydi -> mas'ul/SMM'ga bildirishnoma (tasdiqlash emas)."""
    from apps.accounts.models import User
    from apps.core.notify import notify
    item = get_obj(request, ContentItem, pk, "calendar.edit")
    who = request.user.get_full_name() or request.user.username
    note = (request.POST.get("note") or "").strip()[:300]
    users = [item.assignee] if item.assignee_id else []
    if not users and item.created_by_id and item.created_by_id != request.user.pk:
        users = [item.created_by]
    if not users:
        users = [u for u in User.objects.filter(is_active=True) if u.pk != request.user.pk and not u.is_admin and perms.can(u, "calendar.edit", item.business)]
    if item.design_status != "ready":
        from apps.content import workflow
        item.design_status = "ready"
        item.save(update_fields=["design_status"])
        workflow.add_comment(item, request.user, "Holat: Tayyor — ko'rib chiqing" + (f". {note}" if note else ""), kind="status")
    n = notify("content.ready", f"Tayyor: {item.title or 'kontent'}", f"{who} faylni tayyorladi, ko'rib chiqing." + (f"\nIzoh: {note}" if note else ""),
               business_id=item.business_id, link=f"/kalendar/{item.pk}/", users=users)
    audit("content.ready", user=request.user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title, "note": note})
    messages.success(request, f"«Tayyor» belgisi yuborildi ({n} kishiga)." if n else "Bildirishnoma oluvchi topilmadi (mas'ul tayinlang).")
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
    from apps.metrics.models import Story, StoryMetricsHistory
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
    tabs = "".join(f'<a class="pill{" on" if p == plat else ""}" style="{"background:#2563eb;color:#fff" if p == plat else ""}" href="?p={p}&days={days}">{PLAT_NAMES[p]} <small>({nposts[p]})</small></a> ' for p in plats)
    rng = "".join(f'<a class="pill" href="?p={plat}&days={d}">{d} kun</a> ' for d in (7, 30, 90))
    blocks = [{"type": "html", "html": f'<div class="row sb"><div>{tabs}</div><div>{rng}</div></div>'}]
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
def post_insight(request, pk):
    post = get_obj(request, Post, pk, "analytics.view")
    from apps.studio.models import PostInsight
    from apps.studio.services import why_worked
    ins = post.insights.order_by("-created_at").first() if hasattr(post, "insights") else PostInsight.objects.filter(post=post).order_by("-created_at").first()
    if request.method == "POST":
        if not perms.can(request.user, "ai_studio.create", post.business):
            raise PermissionDenied
        try:
            ins = why_worked(post, request.user)
        except Exception as e:  # noqa: BLE001
            messages.error(request, getattr(e, "user_message_uz", None) or f"AI xatosi: {e}")
        return redirect("post_insight", pk=post.pk)
    nums = an.numeric_basis(post)
    blocks = [{"type": "text", "title": "Post", "text": post.text or "(matnsiz)"},
              ui.kv("Raqamlar (AI shu raqamlarga tayanadi)", [(k, v) for k, v in nums.items()])]
    if ins:
        d = ins.data or {}
        blocks.append({"type": "text", "title": f"Xulosa ({ins.verdict})", "text": ins.text})
        for key, ttl in (("reasons", "Sabablar"), ("repeat", "Takrorlash"), ("change", "O'zgartirish")):
            if d.get(key):
                blocks.append({"type": "text", "title": ttl, "text": "\n".join("• " + str(x) for x in d[key])})
    blocks.append({"type": "actions", "title": "AI tahlil", "buttons": [ui.btn("«Nega ishladi?» tahlilini yaratish", f"/tahlil/post/{post.pk}/", "primary")]})
    return ui.page(request, "Nega ishladi?", blocks, toolbar=[{"label": "Orqaga", "url": "/tahlil/"}])


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
