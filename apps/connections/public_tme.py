"""Ochiq t.me/s/<kanal> sahifasi (akkauntsiz). Sessiyasiz, sekin va ehtiyotkor."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import requests

from apps.core import ratelimit

from .base import (AccountStats, MediaType, NotFoundError, Page, PostData, PostMetrics, RateLimitError,
                   TransientError)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def _num(s: str) -> int | None:
    s = s.strip().replace(" ", "").replace("\xa0", "")
    m = re.match(r"^([\d.,]+)([KMkm]?)$", s)
    if not m:
        return None
    n = float(m.group(1).replace(",", ".")) if m.group(2) else float(m.group(1).replace(",", "").replace(".", ""))
    mult = {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1)
    return int(n * mult)


def parse_channel_html(page: str) -> dict:
    """HTML dan: obunachi soni, postlar. Sof funksiya (testlanadi)."""
    info = {"followers": None, "title": None, "posts": []}
    m = re.search(r'tgme_channel_info_counter">\s*<span class="counter_value">([^<]+)</span>\s*<span class="counter_type">subscribers?</span>', page)
    if m:
        info["followers"] = _num(m.group(1))
    m = re.search(r'tgme_channel_info_header_title"[^>]*>\s*<span[^>]*>([^<]+)</span>', page) or \
        re.search(r'<meta property="og:title" content="([^"]+)"', page)
    if m:
        info["title"] = html.unescape(m.group(1)).strip()
    for blk in re.split(r'(?=<div class="tgme_widget_message_wrap)', page)[1:]:
        pm = re.search(r'data-post="([^"/]+)/(\d+)"', blk)
        if not pm:
            continue
        tm = re.search(r'<time[^>]*datetime="([^"]+)"', blk)
        text = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', blk, re.S)
        views = re.search(r'tgme_widget_message_views">([^<]+)<', blk)
        media = MediaType.VIDEO if "tgme_widget_message_video" in blk else (
            MediaType.IMAGE if "tgme_widget_message_photo" in blk else MediaType.TEXT)
        t = re.sub(r"<[^>]+>", " ", text.group(1)).strip() if text else None
        when = datetime.fromisoformat(tm.group(1)) if tm else datetime.now(timezone.utc)
        info["posts"].append({"id": pm.group(2), "channel": pm.group(1), "text": html.unescape(t) if t else None,
                              "views": _num(views.group(1)) if views else None, "type": media, "date": when,
                              "url": f"https://t.me/{pm.group(1)}/{pm.group(2)}"})
    return info


class PublicChannelScraper:
    def __init__(self, handle: str, min_delay: float = 4.0):
        self.handle = handle.lstrip("@").replace("https://t.me/", "").replace("t.me/", "").strip("/")
        self.min_delay = min_delay

    def _get(self, before: str | None = None) -> str:
        ratelimit.throttle("tme_public", self.min_delay, 3.0)
        url = f"https://t.me/s/{self.handle}" + (f"?before={before}" if before else "")
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=25)
        except requests.RequestException as e:
            raise TransientError(str(e)) from e
        if r.status_code == 429:
            raise RateLimitError("t.me 429")
        if r.status_code == 404 or "tgme_page_extra" in r.text and "tgme_widget_message" not in r.text and "Preview channel" not in r.text:
            raise NotFoundError("Kanal topilmadi yoki ochiq emas")
        return r.text

    def fetch_account_stats(self) -> AccountStats:
        info = parse_channel_html(self._get())
        return AccountStats(datetime.now(timezone.utc), info["followers"])

    def fetch_posts(self, since: datetime, cursor: str | None = None, max_pages: int = 3) -> Page:
        out, before, pages = [], cursor, 0
        while pages < max_pages:
            info = parse_channel_html(self._get(before))
            posts = info["posts"]
            if not posts:
                break
            for p in posts:
                if p["date"] >= since:
                    out.append(PostData(f"{p['channel']}/{p['id']}", p["type"], p["text"], p["url"], p["date"],
                                        raw={"views": p["views"]}))
            oldest = min(posts, key=lambda x: int(x["id"]))
            if oldest["date"] < since:
                break
            before = oldest["id"]
            pages += 1
        return Page(out, before)

    def fetch_post_metrics(self, posts: list[PostData]) -> list[PostMetrics]:
        now = datetime.now(timezone.utc)
        return [PostMetrics(p.external_id, now, views=(p.raw or {}).get("views")) for p in posts]
