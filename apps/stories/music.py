"""Story uchun fon musiqasi: Jamendo (bepul API) ro'yxati va rasm/video + audio -> mp4 yig'ish.
USE_FAKES=True (testlar) da tarmoqqa chiqmaydi: soxta ro'yxat va ffmpeg sinus ohangi."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

from django.conf import settings
from django.core.cache import cache

from apps.core.settings_store import get_secret, get_setting

API = "https://api.jamendo.com/v3.0/tracks/"
CLIP_MIN, CLIP_MAX = 10, 30
MAX_AUDIO_MB = 25
BAD_LICENSE = re.compile(r"/by-nc|-nd|/nd|/nc", re.I)   # NC va ND litsenziyalar tijoriy/yig'ish uchun mos emas


class MusicError(Exception):
    def __init__(self, message_uz: str):
        super().__init__(message_uz)
        self.message_uz = message_uz


def _fake() -> bool:
    return bool(getattr(settings, "USE_FAKES", False))


def enabled() -> bool:
    return bool(get_setting("music.jamendo.enabled", True))


def configured() -> bool:
    return _fake() or bool(get_secret("music.jamendo.client_id"))


def clamp_len(n, default=None) -> int:
    try:
        n = int(float(n))
    except (TypeError, ValueError):
        n = int(default or get_setting("music.clip_default", 15))
    return max(CLIP_MIN, min(CLIP_MAX, n))


def _norm(t: dict) -> dict:
    return {"id": str(t.get("id", "")), "name": t.get("name", ""), "artist": t.get("artist_name", ""), "duration": int(t.get("duration") or 0),
            "image": t.get("image", ""), "audio": t.get("audiodownload") or t.get("audio") or "", "stream": t.get("audio") or t.get("audiodownload") or "",
            "license": t.get("license_ccurl", ""), "share": t.get("shareurl", "")}


def _fake_tracks(n: int) -> list[dict]:
    return [{"id": str(9000 + i), "name": f"Test qo'shiq {i + 1}", "artist": f"Ijrochi {i + 1}", "duration": 90 + i * 7, "image": "",
             "audio": f"fake://{9000 + i}", "stream": "", "license": "https://creativecommons.org/licenses/by/3.0/", "share": ""} for i in range(n)]


def _request(extra: dict, limit: int) -> list[dict]:
    import requests
    cid = get_secret("music.jamendo.client_id")
    if not cid:
        raise MusicError("Jamendo kaliti kiritilmagan. Sozlamalar → Musiqa (Jamendo) bo'limiga client_id ni kiriting.")
    params = {"client_id": cid, "format": "json", "limit": limit, "include": "licenses", "audioformat": "mp32", **extra}
    try:
        r = requests.get(API, params=params, timeout=15)
        data = r.json()
    except Exception as e:  # noqa: BLE001
        raise MusicError(f"Jamendo bilan ulanib bo'lmadi: {e}") from e
    h = data.get("headers", {})
    if h.get("status") != "success":
        raise MusicError(f"Jamendo xatosi: {h.get('error_message') or h.get('code') or r.status_code}")
    return data.get("results", [])


def top_tracks(query: str = "") -> list[dict]:
    """Eng mashhur qo'shiqlar (yoki qidiruv). Keshlanadi (API so'rovlarini tejash)."""
    count = max(1, min(50, int(get_setting("music.jamendo.count", 10))))
    query = (query or "").strip()[:60]
    if _fake():
        items = _fake_tracks(count)
        return [t for t in items if query.lower() in t["name"].lower()] if query else items
    key = f"jamendo:{get_setting('music.jamendo.order', 'popularity_week')}:{count}:{query.lower()}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    extra = {"order": "relevance" if query else get_setting("music.jamendo.order", "popularity_week")}
    if query:
        extra["search"] = query
    commercial = bool(get_setting("music.jamendo.commercial_only", True))
    raw = _request(extra, min(200, count * 4 if commercial else count))
    out = []
    for t in raw:
        n = _norm(t)
        if not n["audio"] or n["duration"] < CLIP_MIN:
            continue
        if commercial and (not n["license"] or BAD_LICENSE.search(n["license"])):
            continue
        out.append(n)
        if len(out) >= count:
            break
    cache.set(key, out, max(1, int(get_setting("music.jamendo.cache_min", 120))) * 60)
    return out


def check() -> tuple[bool, str]:
    """Sozlamalar sahifasidagi «tekshirish» tugmasi uchun."""
    try:
        if _fake():
            return True, "Jamendo (test rejimi) ishlayapti."
        items = _request({"order": "popularity_week"}, 3)
        return True, f"Jamendo ulandi — API javob berdi ({len(items)} ta namuna qo'shiq)."
    except MusicError as e:
        return False, e.message_uz


def credit_line(title: str, artist: str) -> str:
    return f"♫ {title} — {artist} (Jamendo)"


# ---------------- Audio yuklash va video yig'ish ----------------
def _download(url: str, dest: str) -> None:
    if url.startswith("fake://") or _fake():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=60", "-c:a", "libmp3lame", dest],
                       check=True, timeout=60)
        return
    if not url.startswith("https://"):
        raise MusicError("Musiqa manzili noto'g'ri.")
    import requests
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            size = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    size += len(chunk)
                    if size > MAX_AUDIO_MB * 1024 * 1024:
                        raise MusicError("Musiqa fayli juda katta.")
                    f.write(chunk)
    except MusicError:
        raise
    except Exception as e:  # noqa: BLE001
        raise MusicError(f"Musiqani yuklab bo'lmadi: {e}") from e


def build_video(media_path: str, kind: str, audio_url: str, start: int, length: int, out_path: str) -> str:
    """Rasm yoki video + audio parcha -> 9:16 mp4. media_path allaqachon 9:16 ga moslangan bo'lishi kerak."""
    length = clamp_len(length)
    start = max(0, int(start or 0))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        audio = os.path.join(tmp, "a.mp3")
        _download(audio_url, audio)
        fade = f"afade=t=in:st=0:d=1,afade=t=out:st={max(length - 1.5, 0)}:d=1.5"
        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p"
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        cmd += ["-stream_loop", "-1", "-i", media_path] if kind == "video" else ["-loop", "1", "-framerate", "30", "-i", media_path]
        cmd += ["-ss", str(start), "-i", audio, "-t", str(length), "-map", "0:v:0", "-map", "1:a:0", "-vf", vf, "-af", fade,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", "30"]
        if kind != "video":
            cmd += ["-tune", "stillimage"]
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-movflags", "+faststart", out_path]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired as e:
            raise MusicError("Video yig'ish juda uzoq davom etdi.") from e
        if p.returncode != 0 or not os.path.exists(out_path):
            raise MusicError("Musiqali video yig'ib bo'lmadi: " + (p.stderr or "")[-200:])
    return out_path
