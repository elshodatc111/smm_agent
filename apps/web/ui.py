"""Umumiy sahifa quruvchi: view'lar `blocks` ro'yxatini beradi, shablon bitta."""
from __future__ import annotations

from apps.core.utils import fmt_dt

from . import spa
from .common import STATUS_CLASS


def link(text, url, sub=None):
    return {"t": text, "u": url, "sub": sub}


def badge(text, status=None, sub=None):
    return {"t": text, "b": STATUS_CLASS.get(status, ""), "sub": sub}


def btn(text, post_url, cls="", confirm=None):
    return {"t": text, "label": text, "post": post_url, "cls": cls, "confirm": confirm}


def dt(v):
    return fmt_dt(v) if v else "—"


def page(request, title, blocks, *, subtitle="", toolbar=None, charts=None):
    return spa.respond(request, spa.page_json(title, blocks, subtitle=subtitle, toolbar=toolbar, charts=charts))


def tabs(items):
    """Yorliqlar qatori: items = [(nom, url, faolmi)] — React'da segmentli boshqaruv sifatida chiziladi."""
    return {"type": "tabs", "items": [{"label": l, "url": u, "active": bool(a)} for l, u, a in items]}


def table(title, columns, rows, empty=None):
    return {"type": "table", "title": title, "columns": columns, "rows": rows, "empty": empty}


def kv(title, items):
    return {"type": "kv", "title": title, "items": items}


def form_block(form, title="", submit="Saqlash", intro="", action=None, hidden=None):
    return {"type": "form", "form": form, "title": title, "submit": submit, "intro": intro, "action": action, "hidden": hidden}


def form_page(request, title, form, *, back=None, submit="Saqlash", intro="", status=200):
    """Bitta forma sahifasi (yaratish/tahrirlash). Xato bo'lsa 422 emas, 200 + maydon xatolari qaytadi."""
    tb = [{"label": "Orqaga", "url": back, "cls": ""}] if back else []
    return spa.respond(request, spa.page_json(title, [form_block(form, submit=submit, intro=intro)], toolbar=tb), status)
