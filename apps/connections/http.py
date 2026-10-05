"""Tashqi HTTP: tezlik cheklovi + xatolarni PlatformError ga o'girish."""
from __future__ import annotations

import requests

from apps.core import ratelimit
from apps.core.logging_utils import scrub

from .base import (AuthError, NotFoundError, PlatformError, QuotaExceededError, RateLimitError,
                   TransientError)

TIMEOUT = 30


def request(method: str, url: str, *, key: str, min_interval: float = 0.3, jitter: float = 0.2,
            **kw) -> requests.Response:
    ratelimit.throttle(key, min_interval, jitter)
    kw.setdefault("timeout", TIMEOUT)
    try:
        resp = requests.request(method, url, **kw)
    except requests.Timeout as e:
        raise TransientError(f"timeout: {scrub(str(e))}") from e
    except requests.RequestException as e:
        raise TransientError(f"tarmoq: {scrub(str(e))}") from e
    raise_for_status(resp)
    return resp


GRAPH_HINTS = {
    "36000": "Rasm nisbati (aspect ratio) Instagram talabiga mos emas. «Media o'lchami» ni tanlang (4:5 yoki 1:1 yoki 9:16).",
    "36001": "Rasm nisbati Instagram talabiga mos emas. «Media o'lchami» ni tanlang.",
    "36003": "Rasm nisbati Instagram talabiga mos emas (4:5 dan 1.91:1 gacha). «Media o'lchami» ni tanlang.",
    "2207001": "Instagram serveri faylni ololmadi. Birozdan keyin qayta urinib ko'ring.",
    "2207003": "Instagram faylni yuklab olish vaqti tugadi (vaqtinchalik havola ochilmayapti).",
    "2207004": "Fayl hajmi Instagram chegarasidan katta (rasm 8 MB gacha).",
    "2207005": "Fayl formati Instagram uchun mos emas (JPEG/PNG rasm, MP4 H.264+AAC video).",
    "2207006": "Media konteyner topilmadi yoki muddati o'tgan. Qayta urinib ko'ring.",
    "2207008": "Media hali tayyor emas. Qayta urinadi.",
    "2207009": "Rasm nisbati mos emas. «Media o'lchami» ni tanlang.",
    "2207010": "Izoh (caption) juda uzun.",
    "2207023": "Media turi noto'g'ri (rasm/video/reels).",
    "2207026": "Video formati mos emas. MP4 (H.264 video + AAC audio) kerak. «Media o'lchami» ni tanlasangiz tizim o'zi o'giradi (ffmpeg kerak).",
    "2207032": "Instagram media yaratolmadi. Qayta urinib ko'ring.",
    "2207042": "Instagram kunlik nashr limitiga yetdi.",
    "2207050": "Instagram akkaunt cheklangan yoki nashrga ruxsat yo'q.",
    "2207057": "Video davomiyligi mos emas (Reels: 3 soniyadan 15 daqiqagacha).",
    "10": "Nashr ruxsati yo'q: Instagram ulanishini qayta qiling va «nashr qilish» ruxsatini bering (instagram_business_content_publish).",
    "200": "Nashr ruxsati yo'q: Instagram ulanishini qayta qiling va barcha ruxsatlarni bering.",
    "190": "Instagram tokeni yaroqsiz yoki muddati tugagan. Ulanishni qayta qiling.",
    "100": "Instagram so'rovida noto'g'ri parametr.",
    "9007": "Media hali tayyor emas.",
}


def _graph_detail(resp: requests.Response) -> str:
    """Meta/Instagram xato javobidan odam o'qiydigan sabab (kod + izoh + o'zbekcha maslahat)."""
    try:
        j = resp.json()
    except ValueError:
        return ""
    e = j.get("error") if isinstance(j, dict) else None
    if not isinstance(e, dict):
        di = (j or {}).get("debug_info") if isinstance(j, dict) else None   # rupload (resumable)
        return scrub(str(di.get("message") or di))[:300] if isinstance(di, dict) else ""
    code, sub = str(e.get("code", "")), str(e.get("error_subcode", ""))
    is_meta = any(h in (resp.url or "") for h in ("facebook.com", "instagram.com"))
    hint = (GRAPH_HINTS.get(sub) or GRAPH_HINTS.get(code) or "") if is_meta else ""
    msg = scrub(str(e.get("error_user_msg") or e.get("message") or ""))[:300]
    tag = f"[{code}/{sub}]" if sub and sub != "None" else f"[{code}]"
    return f"{hint} ({tag} {msg})".strip() if hint else f"{'Instagram/Meta' if is_meta else 'Platforma'} xatosi: {msg} {tag}"


def raise_for_status(resp: requests.Response) -> None:
    if resp.status_code < 400:
        return
    body = scrub(resp.text[:500])
    detail = _graph_detail(resp)
    if detail and resp.status_code == 400:
        raise PlatformError(body, user_message_uz=detail)
    s = resp.status_code
    ra = resp.headers.get("Retry-After")
    retry_after = int(ra) if ra and ra.isdigit() else None
    if s == 429:
        raise RateLimitError(body, retry_after=retry_after)
    if s in (401,):
        raise AuthError(body)
    if s == 403:
        low = resp.text.lower()
        if "quota" in low or "ratelimit" in low or "limit" in low:
            raise QuotaExceededError(body)
        raise AuthError(body, user_message_uz="Ruxsat yo'q yoki token yaroqsiz.")
    if s == 404:
        raise NotFoundError(body)
    if s >= 500:
        raise TransientError(body)
    raise PlatformError(body)
