"""Rasm/videoni kerakli o'lchamga moslash (original fayl o'zgarmaydi, nusxa yaratiladi)."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings

SIZES = {
    "orig": ("Asl holicha (o'zgartirilmasin)", None),
    "ig_4x5": ("Instagram lenta 4:5 — 1080×1350 (tavsiya)", (1080, 1350)),
    "ig_1x1": ("Kvadrat 1:1 — 1080×1080", (1080, 1080)),
    "ig_191": ("Gorizontal 1.91:1 — 1080×566", (1080, 566)),
    "v_9x16": ("Vertikal 9:16 — 1080×1920 (Reels / Stories / Shorts)", (1080, 1920)),
    "h_16x9": ("Gorizontal 16:9 — 1920×1080 (YouTube / Telegram)", (1920, 1080)),
}
FIT_MODES = {"pad": "Butun kadr saqlansin (chetlari xira fon bilan to'ldiriladi)", "crop": "Markazdan qirqilsin (to'liq to'ldiradi)"}


class MediaFitError(Exception):
    pass


def size_choices():
    return [(k, v[0]) for k, v in SIZES.items()]


def target_size(key: str):
    return (SIZES.get(key) or (None, None))[1]


def _out_path(src: str, w: int, h: int, mode: str, ext: str, crop=None) -> Path:
    st = os.stat(src)
    key = hashlib.sha1(f"{src}|{st.st_mtime_ns}|{st.st_size}|{w}x{h}|{mode}|{crop}".encode()).hexdigest()[:16]
    d = Path(settings.MEDIA_ROOT) / "fitted"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}{ext}"


def _crop(crop):
    c = crop or {}
    cl = lambda v, a, b: max(a, min(b, float(v)))
    return cl(c.get("x", 0.5), 0, 1), cl(c.get("y", 0.5), 0, 1), cl(c.get("z", 1), 1, 4)


def fit_image(src: str, w: int, h: int, mode: str = "pad", crop=None) -> str:
    from PIL import Image, ImageFilter, ImageOps
    cx, cy, cz = _crop(crop)
    out = _out_path(src, w, h, mode, ".jpg", (cx, cy, cz) if mode == "crop" else None)
    if out.exists():
        return str(out)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if mode == "crop":
            k = max(w / im.width, h / im.height) * cz
            sw, sh = max(w, round(im.width * k)), max(h, round(im.height * k))
            big = im.resize((sw, sh), Image.LANCZOS)
            left, top = round((sw - w) * cx), round((sh - h) * cy)
            res = big.crop((left, top, left + w, top + h))
        else:
            bg = ImageOps.fit(im, (w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
            fg = ImageOps.contain(im, (w, h), Image.LANCZOS)
            bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
            res = bg
        res.save(out, "JPEG", quality=92, optimize=True)
    return str(out)


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg"))


def fit_video(src: str, w: int, h: int, mode: str = "pad", crop=None) -> str:
    if not have_ffmpeg():
        raise MediaFitError("Videoni moslash uchun ffmpeg kerak (winget install Gyan.FFmpeg), so'ng run.bat ni qayta ishga tushiring.")
    cx, cy, cz = _crop(crop)
    out = _out_path(src, w, h, mode, ".mp4", (cx, cy, cz) if mode == "crop" else None)
    if out.exists():
        return str(out)
    if mode == "crop":
        vf = (f"scale={round(w * cz)}:{round(h * cz)}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h}:x='(in_w-out_w)*{cx:.4f}':y='(in_h-out_h)*{cy:.4f}',setsar=1,fps=30,format=yuv420p")
        cmd = ["ffmpeg", "-y", "-i", src, "-vf", vf]
    else:
        fc = (f"[0:v]split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=24:2[bg];"
              f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,format=yuv420p[v]")
        cmd = ["ffmpeg", "-y", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "0:a?"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
    except subprocess.TimeoutExpired as e:
        raise MediaFitError("Videoni moslash juda uzoq davom etdi.") from e
    if r.returncode != 0 or not out.exists():
        out.unlink(missing_ok=True)
        raise MediaFitError("Videoni o'girib bo'lmadi: " + (r.stderr or "")[-200:])
    return str(out)


def fit_path(path: str, kind: str, key: str, mode: str = "pad", crop=None) -> str:
    size = target_size(key)
    if not size:
        return path
    w, h = size
    return fit_video(path, w, h, mode, crop) if kind == "video" else fit_image(path, w, h, mode, crop)


def auto_instagram_image(path: str) -> str:
    """Instagram lentasi faqat 4:5…1.91:1 nisbatni qabul qiladi; mos kelmasa avtomatik moslanadi."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
    except Exception:  # noqa: BLE001
        return path
    r = w / h if h else 1
    if 0.8 <= r <= 1.91:
        return path
    return fit_image(path, *(SIZES["ig_4x5"][1] if r < 0.8 else SIZES["ig_191"][1]), "pad")


def fit_for_platform(path: str, kind: str, key: str, mode: str, crop, plat: str) -> str:
    """Nashrda ishlatiladigan aynan shu qoida (oldindan ko'rish ham shuni chaqiradi)."""
    key = key or "orig"
    if key != "orig" and (plat == "instagram" or not key.startswith("ig_")):
        return fit_path(path, kind, key, mode or "pad", crop)
    if plat == "instagram" and kind == "image":
        return auto_instagram_image(path)
    return path
