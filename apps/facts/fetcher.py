"""RSS/Atom yig'ish. Xavfsizlik: faqat http(s), hajm cheklovi, DOCTYPE/ENTITY rad etiladi, ichki tarmoq manzillari bloklanadi.
Faqat sarlavha, qisqa parcha va havola saqlanadi (to'liq matn nusxalanmaydi)."""
from __future__ import annotations

import html
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from django.conf import settings

MAX_BYTES = 2_000_000
UA = "SMMPlatforma-FactsBot/1.0 (+RSS reader; contact: admin)"
TAG_RE = re.compile(r"<[^>]+>")
NS = {"atom": "http://www.w3.org/2005/Atom", "content": "http://purl.org/rss/1.0/modules/content/", "dc": "http://purl.org/dc/elements/1.1/"}


class FeedError(Exception):
    pass


def check_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise FeedError("Manzil http:// yoki https:// bilan boshlanishi kerak.")
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(u.hostname, None):
            ip = ipaddress.ip_address(sa[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise FeedError("Ichki tarmoq manzillariga ruxsat yo'q.")
    except socket.gaierror as e:
        raise FeedError(f"Domen topilmadi: {u.hostname}") from e


def clean(text: str, n: int = 900) -> str:
    t = html.unescape(TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", t).strip()[:n]


def _dt(s: str | None):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def parse_feed(data: bytes, limit: int = 40) -> list[dict]:
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data[:20000].lower():
        raise FeedError("Xavfsiz bo'lmagan XML (DOCTYPE/ENTITY) rad etildi.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise FeedError(f"XML o'qilmadi: {e}") from e
    items = []
    tag = root.tag.lower()
    if tag.endswith("feed"):  # Atom
        for e in root.findall("atom:entry", NS)[:limit]:
            link = ""
            for l in e.findall("atom:link", NS):
                if l.get("rel") in (None, "alternate"):
                    link = l.get("href") or link
            items.append({"title": clean(e.findtext("atom:title", "", NS), 300), "url": link,
                          "published_at": _dt(e.findtext("atom:published", None, NS) or e.findtext("atom:updated", None, NS)),
                          "snippet": clean(e.findtext("atom:summary", "", NS) or e.findtext("atom:content", "", NS))})
    else:  # RSS 2.0
        for e in root.iterfind(".//item"):
            if len(items) >= limit:
                break
            items.append({"title": clean(e.findtext("title", ""), 300), "url": (e.findtext("link", "") or "").strip(),
                          "published_at": _dt(e.findtext("pubDate") or e.findtext("dc:date", None, NS)),
                          "snippet": clean(e.findtext("description", "") or e.findtext("content:encoded", "", NS))})
    return [i for i in items if i["title"] and i["url"].startswith("http")]


FAKE_FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Fake</title>
<item><title>Instagram tests longer Reels up to 3 minutes</title><link>https://example.com/a1</link><pubDate>Mon, 05 Oct 2026 08:00:00 +0000</pubDate>
<description>Instagram is testing Reels up to 3 minutes long. Early tests show 27% more watch time for creators using the longer format.</description></item>
<item><title>Designers adopt AI tools in 2026 workflows</title><link>https://example.com/a2</link><pubDate>Sun, 04 Oct 2026 08:00:00 +0000</pubDate>
<description>A survey of 1,200 designers found 64% use AI tools weekly for ideation and mockups.</description></item></channel></rss>"""


def fetch(url: str) -> list[dict]:
    if getattr(settings, "USE_FAKES", False):
        return parse_feed(FAKE_FEED)
    check_url(url)
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9"},
                         timeout=15, stream=True, allow_redirects=True)
        r.raise_for_status()
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > MAX_BYTES:
                raise FeedError("Fayl juda katta (2 MB dan oshdi).")
    except requests.RequestException as e:
        raise FeedError(f"Yuklab bo'lmadi: {str(e)[:160]}") from e
    return parse_feed(data)
