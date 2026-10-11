"""Umumiy sahifa quruvchi: view'lar `blocks` ro'yxatini beradi, shablon bitta."""
from __future__ import annotations

from django.shortcuts import render

from apps.core.utils import fmt_dt
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
    return render(request, "page.html", {"title": title, "subtitle": subtitle, "blocks": blocks,
                                         "toolbar": toolbar or [], "charts": charts or []})


def table(title, columns, rows, empty=None):
    return {"type": "table", "title": title, "columns": columns, "rows": rows, "empty": empty}


def kv(title, items):
    return {"type": "kv", "title": title, "items": items}


def form_block(form, title="", submit="Saqlash", intro="", action=None, hidden=None):
    return {"type": "form", "form": form, "title": title, "submit": submit, "intro": intro, "action": action, "hidden": hidden}
