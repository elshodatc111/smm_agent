"""Cloudflare menyusi: yuklangan fayllar, holati, qo'lda yuklash va o'chirish."""
from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from . import spa
from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.core.audit import audit
from apps.content import temphost
from apps.content.models import TempObject
from apps.core.settings_store import get_setting, set_setting
from apps.jobs.queue import enqueue

STATUS_UZ = {"uploading": ("Yuklanmoqda…", "warn"), "pending": ("Cloudflare'ga…", "warn"), "uploaded": ("Yuklangan", "ok"), "failed": ("Xato", "bad"), "deleted": ("O'chirilgan", "")}
PLAT_UZ = {"telegram": "Telegram", "instagram": "Instagram", "youtube": "YouTube"}


def _scope(request):
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "publish.view").values_list("pk", flat=True))
    return TempObject.objects.filter(Q(business_id__in=ids) | Q(item__business_id__in=ids)).select_related("item", "asset", "business")


def _get(request, pk) -> TempObject:
    o = _scope(request).filter(pk=pk).first()
    if o is None:
        raise Http404
    return o


def _kind(o: TempObject) -> str:
    ext = os.path.splitext(o.filename or o.key)[1].lower()
    return "video" if ext in (".mp4", ".mov", ".m4v", ".webm") else "image" if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif") else "file"


def _split_tags(s: str) -> list[str]:
    return [t.strip().lower()[:30] for t in (s or "").replace(";", ",").split(",") if t.strip()][:10]


def _mb(n: int) -> str:
    return f"{n / 1048576:.1f} MB" if n < 1024 ** 3 else f"{n / 1024 ** 3:.2f} GB"


@login_required
@require_permission("publish.view")
def cloud_home(request):
    objs = _scope(request)
    show = request.GET.get("show", "")
    flt = request.GET.get("status", "")
    if flt == "busy":
        objs = objs.filter(status__in=["uploading", "pending"])
    elif flt in STATUS_UZ:
        objs = objs.filter(status=flt)
    elif show != "all":
        objs = objs.exclude(status="deleted")
    q, tag = request.GET.get("q", "").strip(), request.GET.get("tag", "").strip().lower()
    if q:
        objs = objs.filter(Q(filename__icontains=q) | Q(tags__icontains=q) | Q(item__title__icontains=q))
    if tag:
        objs = objs.filter(tags__icontains=tag)
    all_tags = sorted({t for tg in _scope(request).exclude(tags="").values_list("tags", flat=True) for t in _split_tags(tg)})
    page = Paginator(objs.order_by("-created_at"), 30).get_page(request.GET.get("p"))
    rows = []
    for o in page:
        label, cls = STATUS_UZ.get(o.status, (o.status, ""))
        plats = ""
        if o.item_id:
            plats = ", ".join(sorted({PLAT_UZ.get(t.account.platform, t.account.platform) for t in o.item.targets.select_related("account")}))
        rows.append({"o": o, "kind": _kind(o), "url": temphost.view_url(o), "label": label, "cls": cls, "size": _mb(o.size), "plats": plats,
                     "item_status": o.item.get_status_display() if o.item_id else ""})
    used, limit = temphost.r2_used_bytes(), temphost.r2_limit_bytes()
    r2_ok = temphost.R2Host().available(0)
    kv_ok = bool(get_setting("worker.cloudflare_url"))
    return spa.respond(request, {
        "kind": "cloud", "pager": spa.pager_json(page), "used": _mb(used), "limit": _mb(limit), "pct": min(100, int(used * 100 / limit)) if limit else 0,
        "r2_ok": r2_ok, "kv_ok": kv_ok, "auto": bool(get_setting("cloud.auto_upload", True)), "f": {"status": flt or "", "show": show or "", "q": q, "tag": tag},
        "all_tags": all_tags, "can_edit": bool(perms.can(request.user, "publish.publish", request.business) if request.business else request.user.is_admin),
        "has_business": bool(request.business), "bucket": (lambda: (temphost.r2_bucket() if get_setting("r2.bucket") and not _config_error() else ""))(), "counts": {k: _scope(request).filter(status=k).count() for k in STATUS_UZ},
        "rows": [{"id": r["o"].pk, "name": r["o"].filename or r["o"].key, "kind": r["kind"], "url": r["url"], "status": r["o"].status, "label": r["label"], "cls": r["cls"],
                  "size": r["size"], "backend": r["o"].backend or "", "error": r["o"].error, "tags": r["o"].tags, "item_id": r["o"].item_id,
                  "item_title": (r["o"].item.title or "(nomsiz)") if r["o"].item_id else "", "plats": r["plats"], "item_status": r["item_status"],
                  "at": r["o"].created_at.isoformat(), "progress": r["o"].progress or 0} for r in rows],
        "busy": _scope(request).filter(status__in=["uploading", "pending"]).exists(), "config_error": _config_error()})


def _config_error() -> str:
    if settings.USE_FAKES or not get_setting("r2.bucket"):
        return ""
    try:
        temphost.r2_bucket()
    except Exception as e:  # noqa: BLE001
        return getattr(e, "user_message_uz", str(e))
    return ""


def _need_edit(request):
    if not (request.user.is_admin or (request.business and perms.can(request.user, "publish.publish", request.business))):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied


@login_required
@require_POST
def cloud_upload_manual(request):
    _need_edit(request)
    if not request.business:
        messages.error(request, "Avval biznesni tanlang.")
        return redirect("cloud_home")
    if not temphost.configured(settings.USE_FAKES):
        messages.error(request, "Cloudflare R2 sozlanmagan: Sozlamalar → Kalitlar bo'limida R2 ma'lumotlarini kiriting.")
        return redirect("cloud_home")
    d = os.path.join(str(settings.MEDIA_ROOT), "cloud_manual")
    os.makedirs(d, exist_ok=True)
    n = 0
    for f in request.FILES.getlist("files"):
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v", ".gif", ".pdf"):
            messages.warning(request, f"«{f.name}» yuklanmadi (ruxsat etilgan: rasm, mp4/mov, pdf).")
            continue
        key = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(d, key)
        with open(path, "wb") as out:
            for ch in f.chunks():
                out.write(ch)
        o = TempObject.objects.create(key=key, status="pending", business=request.business, size=f.size, filename=f.name[:200], local_path=path,
                                      tags=",".join(_split_tags(request.POST.get("tags", ""))))
        enqueue("cloud_upload", {"temp_id": o.pk}, queue="media", business_id=request.business.pk, dedupe_key=f"cu:{o.pk}")
        n += 1
    if n:
        audit("cloud.upload", user=request.user, business_id=request.business.pk, target="cloud", detail={"count": n})
        messages.success(request, f"{n} ta fayl yuklash navbatiga qo'yildi. Holati shu sahifada ko'rinadi.")
    return redirect("cloud_home")


_OK_EXT = (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v", ".gif", ".pdf")
MAX_UPLOAD = 2 * 1024 ** 3


def _part_path(o: TempObject) -> str:
    return o.local_path


@login_required
@require_POST
def cloud_chunk_start(request):
    """Brauzerdan bo'laklab yuklashni boshlaydi: {name,size,tags} -> {id, chunk}."""
    _need_edit(request)
    if not request.business:
        return JsonResponse({"detail": "Avval biznesni tanlang."}, status=400)
    if not temphost.configured(settings.USE_FAKES):
        return JsonResponse({"detail": "Cloudflare R2 sozlanmagan: Sozlamalar → Kalitlar."}, status=400)
    err = _config_error()
    if err:
        return JsonResponse({"detail": err}, status=400)
    name = (request.POST.get("name") or "fayl")[:200]
    ext = os.path.splitext(name)[1].lower()
    try:
        size = int(request.POST.get("size") or 0)
    except ValueError:
        size = 0
    if ext not in _OK_EXT:
        return JsonResponse({"detail": f"«{name}» turi qo'llanmaydi (rasm, mp4/mov, pdf)."}, status=400)
    if size <= 0 or size > MAX_UPLOAD:
        return JsonResponse({"detail": "Fayl hajmi 2 GB dan oshmasligi kerak."}, status=400)
    d = os.path.join(str(settings.MEDIA_ROOT), "cloud_manual")
    os.makedirs(d, exist_ok=True)
    key = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(d, key)
    open(path, "wb").close()
    o = TempObject.objects.create(key=key, status="uploading", business=request.business, size=size, filename=name, local_path=path,
                                  tags=",".join(_split_tags(request.POST.get("tags", ""))))
    return JsonResponse({"id": o.pk, "chunk": CHUNK})


CHUNK = 8 * 1024 * 1024


@login_required
@require_POST
def cloud_chunk_put(request, pk):
    """Bitta bo'lak: file=<bo'lak>, offset=<boshlanish>. Qayta yuborilsa (offset bir xil) ustiga yozadi — uzilgan joydan davom etadi."""
    _need_edit(request)
    o = _get(request, pk)
    f = request.FILES.get("chunk")
    if o.status != "uploading" or not f or not o.local_path:
        return JsonResponse({"detail": "Yuklash faol emas."}, status=400)
    try:
        offset = int(request.POST.get("offset", "0"))
    except ValueError:
        return JsonResponse({"detail": "offset noto'g'ri"}, status=400)
    have = os.path.getsize(o.local_path) if os.path.exists(o.local_path) else 0
    if offset > have or offset + f.size > o.size + 1024:
        return JsonResponse({"detail": "Bo'lak tartibi buzildi", "have": have}, status=409)
    with open(o.local_path, "r+b") as out:
        out.seek(offset)
        out.truncate(offset)
        for ch in f.chunks():
            out.write(ch)
    got = offset + f.size
    o.progress = min(99, int(got * 100 / max(o.size, 1)))
    o.save(update_fields=["progress"])
    return JsonResponse({"ok": True, "have": got})


@login_required
@require_POST
def cloud_chunk_done(request, pk):
    _need_edit(request)
    o = _get(request, pk)
    if o.status != "uploading":
        return JsonResponse({"detail": "Yuklash faol emas."}, status=400)
    have = os.path.getsize(o.local_path) if o.local_path and os.path.exists(o.local_path) else 0
    if have != o.size:
        return JsonResponse({"detail": f"Fayl to'liq kelmadi ({have} / {o.size} bayt). Qayta yuklang."}, status=409)
    o.status, o.progress = "pending", 0
    o.save(update_fields=["status", "progress"])
    enqueue("cloud_upload", {"temp_id": o.pk}, queue="media", business_id=o.business_id, dedupe_key=f"cu:{o.pk}")
    audit("cloud.upload", user=request.user, business_id=o.business_id, target=f"cloud:{o.pk}", detail={"file": o.filename, "size": o.size})
    return JsonResponse({"ok": True})


@login_required
@require_POST
def cloud_delete(request, pk):
    _need_edit(request)
    o = _get(request, pk)
    if o.status != "deleted":
        temphost.delete_object(o, fake=settings.USE_FAKES)
        if o.local_path and not o.asset_id:
            try:
                os.remove(o.local_path)
            except OSError:
                pass
    audit("cloud.delete", user=request.user, business_id=o.business_id or (o.item.business_id if o.item_id else None), target=f"cloud:{o.pk}", detail={"file": o.filename})
    messages.success(request, f"«{o.filename or o.key}» Cloudflare'dan o'chirildi.")
    return redirect(request.POST.get("next") or "cloud_home")


@login_required
@require_POST
def cloud_delete_many(request):
    _need_edit(request)
    ids = [int(x) for x in request.POST.getlist("ids") if x.isdigit()]
    n = 0
    for o in _scope(request).filter(pk__in=ids).exclude(status="deleted"):
        temphost.delete_object(o, fake=settings.USE_FAKES)
        n += 1
    audit("cloud.delete_many", user=request.user, business_id=getattr(request.business, "pk", None), target="cloud", detail={"count": n})
    messages.success(request, f"{n} ta fayl o'chirildi.") if n else messages.info(request, "Hech narsa tanlanmadi.")
    return redirect("cloud_home")


@login_required
@require_POST
def cloud_cleanup_published(request):
    """Nashr bo'lib bo'lgan postlarning fayllarini o'chiradi (xato va kutayotganlariga tegmaydi)."""
    _need_edit(request)
    n = 0
    for o in _scope(request).filter(status="uploaded", item__isnull=False):
        if not o.item.targets.exclude(status="published").exists() and o.item.targets.exists():
            temphost.delete_object(o, fake=settings.USE_FAKES)
            n += 1
    messages.success(request, f"Nashr bo'lgan postlarning {n} ta fayli o'chirildi.")
    return redirect("cloud_home")


@login_required
@require_POST
def cloud_retry(request, pk):
    _need_edit(request)
    o = _get(request, pk)
    if o.status in ("failed", "pending"):
        o.status, o.error = "pending", ""
        o.save(update_fields=["status", "error"])
        enqueue("cloud_upload", {"temp_id": o.pk}, queue="media", business_id=o.business_id or (o.item.business_id if o.item_id else None), dedupe_key=f"cu:{o.pk}:{int(o.created_at.timestamp())}:r")
        messages.success(request, "Qayta yuklash navbatga qo'yildi.")
    return redirect("cloud_home")


@login_required
@require_POST
def cloud_link(request, pk):
    o = _get(request, pk)
    return JsonResponse({"url": temphost.fresh_url(o, 7 * 24 * 3600) if o.status == "uploaded" else ""})


@login_required
@require_POST
def cloud_test(request):
    _need_edit(request)
    if not temphost.R2Host().available(0):
        messages.error(request, "R2 ma'lumotlari to'liq emas (Account ID, Access Key, Secret, Bucket).")
    else:
        err = temphost.R2Host().test()
        messages.success(request, f"R2 ulanishi ishlayapti (bucket «{get_setting('r2.bucket')}»).") if not err else messages.error(request, f"R2 ulanmadi: {err}")
    return redirect("cloud_home")


@login_required
@require_POST
def cloud_auto(request):
    _need_edit(request)
    new = not get_setting("cloud.auto_upload", True)
    set_setting("cloud.auto_upload", new, user=request.user)
    messages.success(request, "Postga yuklangan media Cloudflare'ga avtomatik yuklanadi." if new else "Avtomatik yuklash o'chirildi (faqat nashr paytida kerak bo'lsa yuklanadi).")
    return redirect("cloud_home")


@login_required
def cloud_pick(request):
    """Post formasida «Cloudflare'dan tanlash» oynasi uchun fayllar ro'yxati (JSON)."""
    if not request.business:
        return JsonResponse({"error": "Avval biznesni tanlang."})
    want = [k for k in request.GET.get("kind", "image,video").split(",") if k in ("image", "video")]
    q = request.GET.get("q", "").strip().lower()
    out = []
    for o in _scope(request).filter(status__in=["uploaded", "pending"]).order_by("-created_at")[:120]:
        k = _kind(o)
        hay = f"{o.filename} {o.tags} {o.item.title if o.item_id else ''}".lower()
        if k not in want or (q and q not in hay):
            continue
        out.append({"id": o.pk, "name": o.filename or o.key, "tags": _split_tags(o.tags), "kind": k, "size": _mb(o.size), "ready": o.status == "uploaded",
                    "url": temphost.view_url(o) if o.status == "uploaded" else "", "post": o.item.title if o.item_id else "", "at": o.created_at.strftime("%d.%m.%Y %H:%M")})
    return JsonResponse({"files": out})


@login_required
@require_POST
def cloud_tags(request, pk):
    _need_edit(request)
    o = _get(request, pk)
    o.tags = ",".join(_split_tags(request.POST.get("tags", "")))
    o.save(update_fields=["tags"])
    audit("cloud.tags", user=request.user, business_id=o.business_id or (o.item.business_id if o.item_id else None), target=f"cloud:{o.pk}", detail={"file": o.filename, "tags": o.tags})
    if request.headers.get("X-Requested-With") == "fetch":
        return JsonResponse({"tags": _split_tags(o.tags)})
    messages.success(request, "Teglar saqlandi.")
    return redirect(request.POST.get("next") or "cloud_home")


@login_required
def cloud_file(request, pk):
    """Faylni o'z domenimiz orqali beradi (brauzerda tahrirlash/kesish uchun: CORS muammosi bo'lmasin)."""
    import mimetypes
    import requests
    from django.http import HttpResponse
    o = _get(request, pk)
    if o.status != "uploaded":
        raise Http404
    ctype = mimetypes.guess_type(o.filename or o.key)[0] or "application/octet-stream"
    if o.asset_id and o.asset.file and os.path.exists(o.asset.file.path):
        with open(o.asset.file.path, "rb") as fh:
            return HttpResponse(fh.read(), content_type=ctype)
    try:
        r = requests.get(temphost.view_url(o), timeout=120)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        raise Http404
    return HttpResponse(r.content, content_type=ctype)
