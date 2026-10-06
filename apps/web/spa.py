"""React (SPA) bilan aloqa qatlami.

Qoida: veb-sahifa view'lari HTML emas, JSON qaytaradi (`respond`). Brauzerning oddiy sahifa so'rovi
(`Accept: text/html`) esa `/app/...` ga yo'naltiriladi, u yerda React ilovasi (`shell`) ochiladi va
shu JSON'larni chizadi. Ya'ni mantiq (ruxsat, biznes konteksti, formalar) view'larda qoladi.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.messages import get_messages
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import Resolver404, resolve
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.core.settings_store import get_setting

APP_PREFIX = "/app"
# Brauzer o'zi ochadigan (sahifa bo'lmagan) hujjat/fayl manzillari — /app/ ga yo'naltirilmaydi.
NON_PAGE_NAMES = {"cloud_file", "content_media", "report_file", "report_view", "report_public", "pwa_manifest", "pwa_sw", "pwa_offline",
                  "brand_logo", "spa_shell", "spa_shell_path", "spa_asset"}
SKIP_PREFIXES = ("/static/", "/api/", "/app", "/media/", "/h/", "/brend/")


def _messages(request) -> list[dict]:
    try:
        return [{"level": m.level_tag, "text": str(m)} for m in get_messages(request)]
    except Exception:  # noqa: BLE001
        return []


class SpaEncoder(DjangoJSONEncoder):
    """Shablonlarda avtomatik chaqirilgan metodlar (masalan `user.display`) va model obyektlari ham JSON bo'ladi."""

    def default(self, o):
        if callable(o):
            try:
                return o()
            except TypeError:
                return str(o)
        try:
            return super().default(o)
        except TypeError:
            return str(o)


def respond(request, data: dict, status: int = 200) -> JsonResponse:
    """Sahifa JSON'i + bir martalik xabarlar (flash). Unicode o'zgarmas holda."""
    return JsonResponse({**data, "messages": _messages(request)}, status=status, encoder=SpaEncoder, json_dumps_params={"ensure_ascii": False})


# ------------------------------------------------------------------ formalar
_INPUT_KIND = {"text": "text", "number": "number", "email": "email", "url": "url", "password": "password", "date": "date", "time": "time",
               "datetime-local": "datetime-local", "hidden": "hidden", "color": "color", "tel": "text", "file": "file", "checkbox": "checkbox"}


def _json_safe(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, tuple, set)):
        return [_json_safe(x) for x in v]
    if hasattr(v, "isoformat"):
        return v.isoformat(timespec="minutes") if hasattr(v, "hour") else v.isoformat()
    return str(v)


def _widget_kind(bf) -> str:
    w = bf.field.widget
    if isinstance(w, forms.CheckboxSelectMultiple):
        return "checkboxes"
    if isinstance(w, forms.SelectMultiple):
        return "multiselect"
    if isinstance(w, forms.RadioSelect):
        return "radio"
    if isinstance(w, forms.Select):
        return "select"
    if isinstance(w, forms.Textarea):
        return "textarea"
    if isinstance(w, forms.CheckboxInput):
        return "checkbox"
    if isinstance(w, forms.FileInput):
        return "file"
    return _INPUT_KIND.get(getattr(w, "input_type", "text"), "text")


def form_schema(form: forms.BaseForm) -> dict:
    """Django formasini React uchun tavsifga aylantiradi (qiymatlar, xatolar, variantlar bilan)."""
    fields = []
    for bf in form:
        kind = _widget_kind(bf)
        w = bf.field.widget
        attrs = {k: v for k, v in (w.attrs or {}).items() if k in ("placeholder", "rows", "min", "max", "step", "accept", "maxlength", "autocomplete")}
        for k in ("min_value", "max_value"):
            v = getattr(bf.field, k, None)
            if v is not None:
                attrs["min" if k == "min_value" else "max"] = _json_safe(v)
        item = {"name": bf.html_name, "id": bf.id_for_label, "label": bf.label, "kind": kind, "required": bf.field.required, "help": str(bf.help_text or ""),
                "errors": [str(e) for e in bf.errors], "attrs": attrs, "disabled": bool(bf.field.disabled)}
        if kind in ("select", "multiselect", "radio", "checkboxes"):
            item["choices"] = [[_json_safe(v), str(l)] for v, l in bf.field.choices if not isinstance(l, (list, tuple))]
        if kind != "file":
            val = bf.value()
            item["value"] = _json_safe(val if kind not in ("password",) else "")
        fields.append(item)
    return {"fields": fields, "errors": [str(e) for e in form.non_field_errors()], "multipart": form.is_multipart()}


def pager_json(page) -> dict:
    """Django Page -> {n, pages, count} (React sahifalash tugmalari uchun)."""
    return {"n": page.number, "pages": page.paginator.num_pages, "count": page.paginator.count}


def block_json(block: dict) -> dict:
    if block.get("type") == "form":
        out = {k: v for k, v in block.items() if k != "form"}
        out["form"] = form_schema(block["form"])
        return out
    return block


def page_json(title: str, blocks: list, *, subtitle: str = "", toolbar: list | None = None, charts: list | None = None) -> dict:
    return {"kind": "page", "title": title, "subtitle": subtitle, "toolbar": toolbar or [], "blocks": [block_json(b) for b in blocks], "charts": charts or []}


# ------------------------------------------------------------------ brauzer navigatsiyasi -> /app/
class SpaNavigationMiddleware:
    """Oddiy brauzer sahifa so'rovini (Accept: text/html) React ilovasiga yo'naltiradi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET" and "text/html" in request.headers.get("Accept", "") and not request.path.startswith(SKIP_PREFIXES) and not request.GET.get("csv"):
            try:
                name = resolve(request.path_info).url_name
            except Resolver404:
                name = None
            if name not in NON_PAGE_NAMES:
                q = request.META.get("QUERY_STRING")
                return HttpResponseRedirect(APP_PREFIX + request.path + (f"?{q}" if q else ""))
        return self.get_response(request)


# ------------------------------------------------------------------ React qobig'i
def brand_payload() -> dict:
    return {"name": get_setting("general.system_name", "SMM Platforma"), "brand_color": get_setting("general.brand_color", "#E11D2E"),
            "theme": get_setting("general.theme_default", "light"), "logo": logo_url()}


def logo_url() -> str:
    rel = get_setting("general.agency_logo", "") or ""
    return f"/brend/logo/?v={abs(hash(rel)) % 100000}" if rel and (Path(settings.MEDIA_ROOT) / rel).exists() else ""


SPA_DIR = Path(settings.BASE_DIR) / "static" / "spa"
_MISSING = """<!doctype html><meta charset="utf-8"><title>Frontend yig'ilmagan</title>
<body style="font:16px system-ui;max-width:640px;margin:10vh auto;padding:0 20px"><h1>Frontend hali yig'ilmagan</h1>
<p><code>build_frontend.bat</code> ni ishga tushiring (Node.js kerak), so'ng <code>restart.bat</code>.</p></body>"""


def asset(request, rel: str):
    """Yig'ilgan frontend fayllari (/static/spa/...): diskdan o'qiladi, shuning uchun yangi build serverni qayta ishga tushirmasdan ham ko'rinadi."""
    import mimetypes

    from django.http import FileResponse, Http404
    f = (SPA_DIR / rel).resolve()
    if SPA_DIR.resolve() not in f.parents or not f.is_file():
        raise Http404
    r = FileResponse(open(f, "rb"), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
    r["Cache-Control"] = "public, max-age=31536000, immutable" if "/assets/" in f.as_posix() else "no-cache"
    return r


@ensure_csrf_cookie
def shell(request, path: str = ""):
    """React ilovasining index.html'i (Vite build natijasi) + boshlang'ich brend ma'lumoti."""
    f = SPA_DIR / "index.html"
    if not f.exists():
        return HttpResponse(_MISSING, status=503)
    html = f.read_text(encoding="utf-8")
    boot = json.dumps({"brand": brand_payload()}, ensure_ascii=False).replace("</", "<\\/")
    b = brand_payload()
    html = re.sub(r"<title>.*?</title>", f"<title>{b['name']}</title>", html, count=1, flags=re.S)
    html = html.replace("</head>", f'<script>window.__BOOT__={boot}</script><meta name="theme-color" content="{b["brand_color"]}"></head>', 1)
    r = HttpResponse(html, content_type="text/html; charset=utf-8")
    r["Cache-Control"] = "no-store"
    return r


# ------------------------------------------------------------------ xato javoblari (JSON)
def _err(request, status: int, title: str, detail: str = ""):
    return JsonResponse({"kind": "error", "status": status, "title": title, "detail": detail, "messages": []}, status=status,
                        json_dumps_params={"ensure_ascii": False})


def error_400(request, exception=None):
    return _err(request, 400, "So'rov noto'g'ri")


def error_403(request, exception=None):
    return _err(request, 403, "Ruxsat yo'q", str(exception or "Bu amal uchun sizda ruxsat yo'q."))


def error_404(request, exception=None):
    return _err(request, 404, "Topilmadi", "So'ralgan sahifa yoki ma'lumot mavjud emas.")


def error_500(request):
    return _err(request, 500, "Server xatosi", "Kutilmagan xato yuz berdi. Xato jurnalga yozildi.")


def csrf_failure(request, reason=""):
    return _err(request, 403, "Seans eskirgan", "Sahifani yangilang va qayta urinib ko'ring.")


def brand_logo(request):
    """Tizim logotipi (kirishdan oldin ham kerak: kirish sahifasi, ikonka). Hech narsa maxfiy emas."""
    from django.http import FileResponse, Http404
    rel = get_setting("general.agency_logo", "") or ""
    f = Path(settings.MEDIA_ROOT) / rel if rel else None
    if not f or not f.is_file() or Path(settings.MEDIA_ROOT).resolve() not in f.resolve().parents:
        raise Http404
    r = FileResponse(open(f, "rb"))
    r["Cache-Control"] = "public, max-age=3600"
    return r
