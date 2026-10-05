"""Aniq oldindan ko'rish: nashrda ishlatiladigan aynan o'sha moslash kodi bilan tayyorlangan rasm."""
from __future__ import annotations

import os
import tempfile

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from apps.accounts.services import perms
from apps.content import mediafit
from apps.content.models import ContentAsset, TempObject


def _png_jpeg(path: str, maxw: int = 1080) -> bytes:
    import io
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if im.width > maxw:
            im = im.resize((maxw, round(im.height * maxw / im.width)))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=88)
        return b.getvalue()


def _dims(path: str) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


@login_required
@require_POST
def fit_preview(request):
    """POST: size, fit, cx, cy, cz, plat + (aid | cloud_id | file). Javob: JPEG (X-Dims sarlavhasida o'lcham)."""
    key = request.POST.get("size") or "orig"
    mode = request.POST.get("fit") or "pad"
    plat = request.POST.get("plat") or ""
    try:
        crop = {"x": float(request.POST.get("cx", .5)), "y": float(request.POST.get("cy", .5)), "z": float(request.POST.get("cz", 1))}
    except ValueError:
        crop = {"x": .5, "y": .5, "z": 1}
    src, tmp = None, None
    try:
        if request.POST.get("aid", "").isdigit():
            a = ContentAsset.objects.filter(pk=int(request.POST["aid"])).select_related("item").first()
            if not a or not perms.has_business(request.user, a.item.business_id) or not perms.can(request.user, "calendar.view", a.item.business):
                return JsonResponse({"error": "Topilmadi"}, status=404)
            if a.kind != "image":
                return JsonResponse({"error": "Video uchun aniq ko'rinish rasm kadri sifatida ko'rsatilmaydi."}, status=400)
            src = a.file.path
        elif request.POST.get("cloud_id", "").isdigit():
            o = TempObject.objects.filter(pk=int(request.POST["cloud_id"]), status="uploaded").first()
            if not o or not o.business_id or not perms.has_business(request.user, o.business_id):
                return JsonResponse({"error": "Topilmadi"}, status=404)
            if o.asset_id and o.asset.file and os.path.exists(o.asset.file.path):
                src = o.asset.file.path
            else:
                import requests
                from apps.content import temphost
                r = requests.get(temphost.view_url(o), timeout=60)
                r.raise_for_status()
                fd, tmp = tempfile.mkstemp(suffix=".img")
                os.write(fd, r.content)
                os.close(fd)
                src = tmp
        elif request.FILES.get("file"):
            f = request.FILES["file"]
            if (f.content_type or "").startswith("video") or f.size > 40 * 1024 * 1024:
                return JsonResponse({"error": "Faqat rasm (40 MB gacha)."}, status=400)
            fd, tmp = tempfile.mkstemp(suffix=".img")
            for ch in f.chunks():
                os.write(fd, ch)
            os.close(fd)
            src = tmp
        else:
            return JsonResponse({"error": "Fayl ko'rsatilmadi"}, status=400)
        out = mediafit.fit_for_platform(src, "image", key, mode, crop, plat)
        w, h = _dims(out)
        data = _png_jpeg(out)
        if tmp and out != src:
            try:
                os.unlink(out)
            except OSError:
                pass
        r = HttpResponse(data, content_type="image/jpeg")
        r["X-Dims"] = f"{w}x{h}"
        r["Cache-Control"] = "no-store"
        return r
    except Exception as e:  # noqa: BLE001
        return JsonResponse({"error": f"Ko'rinishni tayyorlab bo'lmadi: {str(e)[:120]}"}, status=400)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
