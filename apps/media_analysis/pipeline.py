"""Gibrid media tahlil (TZ 4.10): lokal (ffmpeg/Pillow/OpenCV) -> STT -> bitta bulutli AI so'rovi -> kesh."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time


from apps.ai_router.router import AIRouter, AIUnavailable, generate
from apps.ai_router.types import AIRequest, Attachment, TaskType
from apps.core.settings_store import get_setting

from .models import MediaAnalysis, MediaFile


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def probe(path: str) -> dict:
    r = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path], 60)
    j = json.loads(r.stdout or "{}")
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in j.get("streams", []) if s.get("codec_type") == "audio"), None)
    fps = 0.0
    if v.get("r_frame_rate") and "/" in v["r_frame_rate"]:
        n, d = v["r_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else 0.0
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    dur = float(j.get("format", {}).get("duration", 0) or 0)
    return {"duration": dur, "width": w, "height": h, "aspect": round(w / h, 3) if h else None, "fps": round(fps, 2),
            "has_audio": a is not None, "size": int(j.get("format", {}).get("size", 0) or 0), "codec": v.get("codec_name")}


def scenes(path: str, threshold: float = 0.35) -> list[float]:
    r = _run(["ffmpeg", "-hide_banner", "-i", path, "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"], 600)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def keyframes(path: str, outdir: str, duration: float, scene_times: list[float], n: int = 12) -> list[str]:
    n = max(8, min(16, n))
    times = sorted(set([round(duration * (i + 0.5) / n, 2) for i in range(n)] + [round(t + 0.2, 2) for t in scene_times[:4]]))[:16]
    out = []
    for i, t in enumerate(times):
        p = os.path.join(outdir, f"k{i:02d}.jpg")
        _run(["ffmpeg", "-y", "-ss", str(t), "-i", path, "-frames:v", "1", "-vf", "scale='min(768,iw)':-2", "-q:v", "4", p], 60)
        if os.path.exists(p):
            out.append(p)
    return out


def extract_audio(path: str, outdir: str) -> str | None:
    p = os.path.join(outdir, "audio.mp3")
    r = _run(["ffmpeg", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", p], 300)
    return p if os.path.exists(p) and os.path.getsize(p) > 1000 else None


def colors_and_faces(frames: list[str]) -> dict:
    out = {"dominant_colors": [], "face_ratio": None}
    try:
        from PIL import Image
        cols = []
        for fp in frames[:6]:
            with Image.open(fp) as im:
                q = im.convert("RGB").resize((64, 64)).quantize(3).convert("RGB")
                cols += [c for _, c in sorted(q.getcolors(), reverse=True)[:2]]
        from collections import Counter
        out["dominant_colors"] = ["#%02x%02x%02x" % c for c, _ in Counter(cols).most_common(3)]
    except Exception:  # noqa: BLE001
        pass
    try:
        import cv2  # ixtiyoriy
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        hits = 0
        for fp in frames:
            g = cv2.cvtColor(cv2.imread(fp), cv2.COLOR_BGR2GRAY)
            hits += len(det.detectMultiScale(g, 1.2, 5)) > 0
        out["face_ratio"] = round(hits / max(1, len(frames)), 2)
    except Exception:  # noqa: BLE001
        pass
    return out


def confidence_from(extra: dict) -> float:
    lp = extra.get("avg_logprob")
    base = math.exp(lp) if isinstance(lp, (int, float)) else 0.6
    base *= (1 - float(extra.get("no_speech_prob", 0) or 0))
    if float(extra.get("compression_ratio", 1) or 1) > 2.4:
        base *= 0.7
    return round(max(0.0, min(1.0, base)), 2)


def transcribe(audio_path: str, router: AIRouter) -> dict | None:
    with open(audio_path, "rb") as f:
        data = f.read()
    if len(data) > 24 * 1024 * 1024:
        return None
    req = AIRequest(task=TaskType.STT, prompt="", attachments=[Attachment("audio/mpeg", data, "audio.mp3")],
                    require_lang=None, cache_ttl_sec=0, options={"language": "uz", "prompt": get_setting("stt.uz_prompt", "")})
    try:
        res = router.run(req)
    except AIUnavailable:
        return None
    conf = confidence_from(res.extra or {})
    return {"text": res.text, "provider": res.provider, "confidence": conf,
            "reliable": conf >= float(get_setting("stt.min_confidence", 0.55)), "language": "uz"}


VISION_SCHEMA_HINT = ('Faqat JSON qaytar: {"verdict":"chiqarish|tuzatish|qayta_tayyorlash","verdict_reason":"1 jumla","score":0-100,'
                      '"scores":{"hook":0-10,"visual":0-10,"pacing":0-10,"audio_text":0-10,"cta":0-10,"brand_fit":0-10},'
                      '"hook":{"text":"dastlabki 3 soniyada nima bor","strength":0-10},"cta":{"present":true,"text":"","clarity":0-10},'
                      '"scenes":[{"t":"0-3s","what":"nima ko\'rinadi/aytiladi","attention":0-10,"note":"qisqa izoh"}],'
                      '"platform_fit":{"instagram_reels":0-10,"shorts":0-10,"telegram":0-10,"instagram_feed":0-10},'
                      '"pacing":"sekin|o\'rtacha|tez","strengths":["qisqa"],"improvements":[{"fix":"aniq tuzatish","priority":"yuqori|o\'rta|past"}],"summary":"2 jumla"}. '
                      'Sahnalarni vaqt bo\'yicha ketma-ket yoz (6-10 ta), hamma matn o\'zbekcha, qisqa va aniq.')


def analyze_media(media: MediaFile, router: AIRouter | None = None, progress=None) -> MediaAnalysis:
    t0 = time.monotonic()
    path = media.file.path
    sha = media.sha256 or sha256_file(path)
    cached = MediaAnalysis.objects.filter(sha256=sha).first()
    if cached and cached.media_id != media.pk:
        new = MediaAnalysis.objects.create(media=media, sha256=sha, technical=cached.technical, transcript=cached.transcript,
                                           ai=cached.ai, degraded=cached.degraded, step_results={"cached_from": cached.pk}, took_sec=0)
        return new
    router = router or AIRouter()
    tmp = tempfile.mkdtemp(prefix="smm_media_")
    steps: dict = {}
    try:
        tech = probe(path)
        steps["probe"] = True
        if progress: progress(10)
        frames, transcript = [], None
        if media.kind == "video":
            sc = scenes(path)
            dur = tech["duration"] or 1
            tech.update({"scene_count": len(sc) + 1, "cuts_per_min": round(len(sc) / dur * 60, 1)})
            steps["scenes"] = True
            if progress: progress(30)
            frames = keyframes(path, tmp, dur, sc)
            tech.update(colors_and_faces(frames))
            if progress: progress(50)
            if tech["has_audio"]:
                ap = extract_audio(path, tmp)
                if ap:
                    transcript = transcribe(ap, router)
                    steps["stt"] = bool(transcript)
        else:
            frames = [path]
            tech.update(colors_and_faces(frames))
        if progress: progress(70)
        ai, degraded = None, False
        try:
            atts = [Attachment("image/jpeg", open(f, "rb").read(), os.path.basename(f)) for f in frames[:16]]
            tr_text = ""
            if transcript:
                tr_text = f"\nTranskript (ishonch {transcript['confidence']}, {'ishonchli' if transcript['reliable'] else 'ISHONCHSIZ — og`irligini kamaytir'}): {transcript['text'][:2500]}"
            prompt = (f"Bu {media.kind} ni tahlil qil. Texnik ma'lumot: {json.dumps(tech, ensure_ascii=False)}.{tr_text}\n"
                      f"Kadrlar ilova qilingan. Brend mosligini baholash uchun brend xotirasidan foydalan. {VISION_SCHEMA_HINT}")
            res, _ = generate(TaskType.VISION, prompt, business=media.business, kind="media", schema={"json": True},
                              router=router, attachments=atts, cache_ttl_sec=0)
            ai = res.data
        except AIUnavailable:
            degraded = True
        steps["vision"] = ai is not None
        if progress: progress(95)
        return MediaAnalysis.objects.create(media=media, sha256=sha, technical=tech, transcript=transcript, ai=ai,
                                            degraded=degraded, step_results=steps, took_sec=round(time.monotonic() - t0, 1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
