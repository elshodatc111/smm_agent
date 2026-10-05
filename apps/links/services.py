"""Cloudflare Worker bilan ishlash. Faqat chiquvchi ulanish: tizim Worker'ga murojaat qiladi."""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from django.conf import settings

from apps.connections.base import PlatformError, TransientError
from apps.core.settings_store import get_secret, get_setting

from .models import LinkClick, ShortLink, WorkerStatus


class FakeWorker:
    links: dict = {}
    clicks: list = []
    def put_link(self, slug, data): FakeWorker.links[slug] = data
    def delete_link(self, slug): FakeWorker.links.pop(slug, None)
    def status(self): return {"ok": True, "version": "fake", "clicks_today": len(FakeWorker.clicks)}
    def clicks_after(self, after_id): return [c for c in FakeWorker.clicks if c["id"] > after_id]


class WorkerClient:
    def __init__(self):
        self.base = get_setting("worker.cloudflare_url", "").rstrip("/")
        self.token = get_secret("worker.admin_token")

    def _req(self, method, path, **kw):
        if not self.base or not self.token:
            raise PlatformError("Worker sozlanmagan", user_message_uz="Cloudflare Worker manzili va admin tokeni Sozlamalarda kiritilmagan.")
        try:
            r = requests.request(method, self.base + path, headers={"Authorization": f"Bearer {self.token}"}, timeout=30, **kw)
        except requests.RequestException as e:
            raise TransientError(str(e)) from e
        if r.status_code >= 400:
            raise PlatformError(f"Worker {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    def put_link(self, slug, data): return self._req("PUT", f"/admin/links/{slug}", json=data)
    def delete_link(self, slug): return self._req("DELETE", f"/admin/links/{slug}")
    def status(self): return self._req("GET", "/admin/status")
    def clicks_after(self, after_id): return self._req("GET", "/admin/clicks", params={"after": after_id}).get("clicks", [])


def client():
    return FakeWorker() if settings.USE_FAKES else WorkerClient()


def with_utm(url: str, utm: dict) -> str:
    p = urlparse(url)
    q = dict(parse_qsl(p.query))
    q.update({f"utm_{k}" if not k.startswith("utm_") else k: v for k, v in utm.items() if v})
    return urlunparse(p._replace(query=urlencode(q)))


def new_slug(n=6) -> str:
    alpha = string.ascii_lowercase + string.digits
    while True:
        s = "".join(secrets.choice(alpha) for _ in range(n))
        if not ShortLink.objects.filter(slug=s).exists():
            return s


def short_url(link: ShortLink) -> str:
    return f"{get_setting('worker.cloudflare_url', '').rstrip('/')}/{link.slug}"


def push(link: ShortLink) -> None:
    data = {"url": with_utm(link.target_url, link.utm), "enabled": link.enabled,
            "exp": int(link.expires_at.timestamp()) if link.expires_at else None}
    try:
        client().put_link(link.slug, data)
        link.synced, link.sync_error = True, ""
    except PlatformError as e:
        link.synced, link.sync_error = False, (getattr(e, "user_message_uz", str(e)))[:300]
    link.save(update_fields=["synced", "sync_error"])


def create_link(business, target_url, *, slug=None, utm=None, content_item=None, campaign=None, expires_at=None, note="") -> ShortLink:
    link = ShortLink.objects.create(business=business, slug=slug or new_slug(), target_url=target_url, utm=utm or {},
                                    content_item=content_item, campaign=campaign, expires_at=expires_at, note=note)
    push(link)
    return link


def remove_link(link: ShortLink) -> None:
    try:
        client().delete_link(link.slug)
    except PlatformError:
        pass
    link.delete()


def sync_clicks() -> dict:
    st, _ = WorkerStatus.objects.get_or_create(pk=1)
    c = client()
    try:
        info = c.status()
        st.ok, st.message, st.version = bool(info.get("ok")), "", str(info.get("version", ""))
        st.clicks_today = int(info.get("clicks_today", 0))
        n = 0
        for row in c.clicks_after(st.last_remote_id):
            link = ShortLink.objects.filter(slug=row["slug"]).first()
            if not link:
                continue
            LinkClick.objects.get_or_create(remote_id=row["id"], defaults=dict(
                link=link, clicked_at=datetime.fromtimestamp(row["t"], timezone.utc), source=row.get("source", "")[:80],
                device=row.get("device", "")[:10], country=row.get("country", "")[:4]))
            st.last_remote_id = max(st.last_remote_id, row["id"])
            n += 1
        st.save()
        return {"clicks": n}
    except PlatformError as e:
        st.ok, st.message = False, getattr(e, "user_message_uz", str(e))[:300]
        st.save()
        raise
