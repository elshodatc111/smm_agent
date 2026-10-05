"""Kontent qoidalari dvigateli (CONTRACTS §8)."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

from apps.ai_router.langcheck import check_uz
from apps.connections.base import RuleProblem

PASS, WARN, BLOCK = "pass", "warn", "block"
ORDER = {PASS: 0, WARN: 1, BLOCK: 2}
NON_DOWNGRADABLE = {"ai.draft_not_reviewed"}  # truth.* ham

PHONE = re.compile(r"(?<!\d)(\+?998[\s\-]?\(?\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\d{2}[\s\-]\d{3}[\s\-]\d{2}[\s\-]\d{2})(?!\d)")
PRICE = re.compile(r"(\d[\d\s.,]*\d|\d)\s*(so'm|som|сум|uzs|\$|usd|ming|mln)", re.I)
PERCENT = re.compile(r"(\d{1,3})\s*%")
CLAIMS = ["100% kafolat", "eng arzon", "yagona", "birinchi o'rinda", "kafolatlangan natija", "hech kim", "eng yaxshi narx", "garantiya"]
SENSITIVE = ["davolaydi", "davolash", "kasallikdan xalos", "tez boyish", "daromad kafolati", "foiz kafolati", "investitsiya", "pul ishlang", "ozish kafolati"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
HASHTAG = re.compile(r"#\w+")


@dataclass
class RuleContext:
    business: object
    platform: str
    brand: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    assets: list = field(default_factory=list)  # [(path, kind)]


@dataclass
class RuleCheckOutcome:
    status: str
    problems: list[RuleProblem]


def _p(rid, sev, msg, field=None, sug=None):
    return RuleProblem(rid, sev, msg, field, sug)


def _norm_num(s: str) -> str:
    return re.sub(r"\D", "", s)


def brand_banned_words(item, ctx):
    words = [w.lower() for w in (ctx.params.get("words") or ctx.brand.get("banned_words") or [])]
    low = (item.text or "").lower()
    hit = [w for w in words if w and w in low]
    return [_p("brand.banned_words", BLOCK, f"Taqiqlangan so'z(lar): {', '.join(hit)}", "text", "Bu so'zlarni olib tashlang.")] if hit else []


def brand_required_words(item, ctx):
    words = [w.lower() for w in (ctx.params.get("words") or [])]
    low = (item.text or "").lower()
    miss = [w for w in words if w and w not in low]
    return [_p("brand.required_words", WARN, f"Majburiy so'z/CTA yo'q: {', '.join(miss)}", "text")] if miss else []


def brand_emoji_level(item, ctx):
    mx = int(ctx.params.get("max", 8))
    n = len(EMOJI.findall(item.text or ""))
    return [_p("brand.emoji_level", WARN, f"Emoji ko'p ({n} ta, tavsiya ≤ {mx}).", "text")] if n > mx else []


LIMITS = {"telegram": (4096, 1024), "instagram": (2200, 2200), "youtube": (5000, 5000)}


def platform_text_length(item, ctx):
    lim_text, lim_cap = LIMITS.get(ctx.platform, (5000, 5000))
    has_media = bool(ctx.assets)
    lim = lim_cap if has_media else lim_text
    n = len(item.text or "")
    out = []
    if n > lim:
        out.append(_p("platform.text_length", BLOCK, f"Matn {n} belgi; {ctx.platform} uchun chegara {lim}.", "text", f"{n - lim} belgiga qisqartiring."))
    if ctx.platform == "youtube":
        title = (item.options.get("title") or (item.text or "").split("\n")[0])
        if len(title) > 100:
            out.append(_p("platform.text_length", BLOCK, "YouTube sarlavhasi 100 belgidan oshmasligi kerak.", "title"))
    return out


def platform_hashtag_count(item, ctx):
    n = len(HASHTAG.findall(item.text or ""))
    lim = {"instagram": 30, "youtube": 15}.get(ctx.platform, 50)
    out = []
    if n > lim:
        out.append(_p("platform.hashtag_count", WARN, f"Hashtag {n} ta; chegara {lim}.", "text"))
    elif ctx.platform == "instagram" and n > 10:
        out.append(_p("platform.hashtag_count", WARN, f"Hashtag {n} ta; tavsiya ≤ 10.", "text"))
    return out


def _probe(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,codec_name",
                            "-show_entries", "format=duration,size", "-of", "default=nw=1", path], capture_output=True, text=True, timeout=30)
        d = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
        return {"w": int(d.get("width", 0)), "h": int(d.get("height", 0)), "dur": float(d.get("duration", 0) or 0),
                "size": int(d.get("size", 0) or 0), "codec": d.get("codec_name", "")}
    except Exception:  # noqa: BLE001
        return None


def platform_video_spec(item, ctx):
    out = []
    if item.media_type not in ("video", "reel", "short", "story"):
        return out
    vids = [p for p, k in ctx.assets if k == "video"]
    if not vids:
        if item.media_type != "story":
            out.append(_p("platform.video_spec", BLOCK, "Video fayl biriktirilmagan.", "media"))
        return out
    info = _probe(vids[0])
    if info is None:
        return [_p("platform.video_spec", WARN, "Videoni tekshirib bo'lmadi (ffprobe yo'q yoki fayl buzuq).", "media")]
    ratio = info["w"] / info["h"] if info["h"] else 0
    if item.media_type in ("reel", "short", "story") and ratio and abs(ratio - 9 / 16) > 0.08 and (item.options or {}).get("media_size", "orig") == "orig":
        out.append(_p("platform.video_spec", WARN, "Vertikal 9:16 nisbat tavsiya etiladi.", "media"))
    mx = {"reel": 900, "short": 180, "story": 60}.get(item.media_type)
    if mx and info["dur"] > mx:
        out.append(_p("platform.video_spec", BLOCK, f"Davomiylik {info['dur']:.0f}s; chegara {mx}s.", "media"))
    size_mb = (info["size"] or os.path.getsize(vids[0])) / 1e6
    cap = {"telegram": 50, "instagram": 1000, "youtube": 128000}.get(ctx.platform, 2000)   # Telegram bot: 50 MB
    if size_mb > cap:
        out.append(_p("platform.video_spec", BLOCK, f"Fayl {size_mb:.0f} MB; {ctx.platform} chegarasi {cap} MB." + (" Videoni kichraytiring (masalan 720p) yoki kanalga qo'lda yuklang." if ctx.platform == "telegram" else ""), "media"))
    return out


def platform_image_spec(item, ctx):
    out = []
    for p, k in ctx.assets:
        if k != "image":
            continue
        try:
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
            mb = os.path.getsize(p) / 1e6
            if ctx.platform == "instagram":
                if mb > 8:
                    out.append(_p("platform.image_spec", BLOCK, f"Rasm {mb:.1f} MB; Instagram chegarasi 8 MB."))
                r = w / h
                if not (0.8 <= r <= 1.91):
                    out.append(_p("platform.image_spec", WARN, "Rasm nisbati Instagram talabiga mos emas — nashrda avtomatik moslanadi (yoki «Media o'lchami» ni o'zingiz tanlang)."))
            elif ctx.platform == "telegram" and (w + h) > 10000:
                out.append(_p("platform.image_spec", BLOCK, "Telegram: rasm o'lchamlari yig'indisi 10000 dan oshmasin."))
        except Exception:  # noqa: BLE001
            out.append(_p("platform.image_spec", WARN, "Rasmni tekshirib bo'lmadi."))
    return out


def platform_media_count(item, ctx):
    """Karusel/albom: fayllar soni; media talab qiladigan turlar: fayl bor-yo'qligi."""
    n = len(ctx.assets)
    mt = item.media_type
    if mt in ("carousel", "album") and not (2 <= n <= 10):
        yield _p("platform.media_count", BLOCK, f"{'Karusel' if mt == 'carousel' else 'Albom'} uchun 2–10 ta fayl kerak, hozir {n} ta.", "files", "Postga yana rasm/video qo'shing.")
    elif mt in ("image", "video", "reel", "short", "story") and n == 0 and ctx.platform in ("instagram", "youtube"):
        yield _p("platform.media_count", BLOCK, "Bu post turi uchun fayl biriktirilmagan.", "files", "Rasm yoki videoni yuklang.")
    elif mt in ("image", "video", "reel", "short", "story") and n > 1 and ctx.platform == "instagram":
        yield _p("platform.media_count", WARN, f"Bu turda faqat birinchi fayl ishlatiladi ({n} ta biriktirilgan). Bir nechta bo'lsa «Karusel» ni tanlang.", "files")


def truth_facts_match(item, ctx):
    facts = getattr(ctx.business, "facts", {}) or {}
    text = item.text or ""
    out = []
    phones_known = {_norm_num(x)[-9:] for x in facts.get("phones", [])} | {_norm_num(x)[-9:] for x in PHONE.findall(ctx.business.contact_info or "")}
    for ph in PHONE.findall(text):
        if _norm_num(ph)[-9:] not in phones_known:
            out.append(_p("truth.facts_match", BLOCK, f"Telefon raqam biznes ma'lumotida yo'q: {ph}", "text", "Raqamni tekshiring yoki Bizneslar bo'limida qo'shing."))
    prices_known = {_norm_num(str(x)) for x in facts.get("prices", [])}
    found = PRICE.findall(text)
    for num, unit in found:
        if prices_known and _norm_num(num) not in prices_known:
            out.append(_p("truth.facts_match", BLOCK, f"Narx biznes ma'lumotida yo'q: {num} {unit}", "text", "Narxni tasdiqlangan ro'yxatdan oling."))
        elif not prices_known:
            out.append(_p("truth.facts_match", WARN, f"Narx tasdiqlanmagan: {num} {unit} (biznes faktlarida narxlar kiritilmagan).", "text"))
    disc_known = {str(x).strip("% ") for x in facts.get("discounts", [])}
    for pct in PERCENT.findall(text):
        if pct not in disc_known:
            out.append(_p("truth.facts_match", BLOCK if disc_known else WARN, f"Chegirma foizi tasdiqlanmagan: {pct}%", "text"))
    return out


def truth_unverified_claim(item, ctx):
    low = (item.text or "").lower()
    hit = [c for c in CLAIMS if c in low]
    return [_p("truth.unverified_claim", WARN, "Isbotlanmagan da'vo: " + ", ".join(hit), "text", "Aniq dalil/raqam bilan almashtiring.")] if hit else []


def _shingles(t: str, n=3):
    w = re.findall(r"\w+", (t or "").lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))} or set(w)


def similarity(a: str, b: str) -> float:
    A, B = _shingles(a), _shingles(b)
    return len(A & B) / len(A | B) if A and B else 0.0


def orig_competitor_similarity(item, ctx):
    from apps.metrics.models import CompetitorPost
    texts = list(CompetitorPost.objects.filter(business_id=ctx.business.pk).exclude(text="").values_list("text", flat=True)[:300])
    try:
        from apps.studio.models import Hook
        texts += list(Hook.objects.filter(source="competitor").values_list("text", flat=True)[:300])
    except Exception:  # noqa: BLE001
        pass
    best = max((similarity(item.text, t) for t in texts), default=0.0)
    blk, wrn = float(ctx.params.get("block", 0.85)), float(ctx.params.get("warn", 0.7))
    if best >= blk:
        return [_p("orig.competitor_similarity", BLOCK, f"Raqobatchi matniga juda o'xshash ({best:.0%}).", "text", "Faqat g'oyani oling, o'z so'zlaringiz bilan yozing.")]
    if best >= wrn:
        return [_p("orig.competitor_similarity", WARN, f"Raqobatchi matniga o'xshash ({best:.0%}).", "text")]
    return []


def policy_sensitive_topic(item, ctx):
    low = (item.text or "").lower()
    hit = [s for s in SENSITIVE if s in low]
    return [_p("policy.sensitive_topic", WARN, "Sog'liq/moliya bo'yicha ehtiyotkor ibora kerak: " + ", ".join(hit), "text")] if hit else []


def policy_copyright_media(item, ctx):
    if item.media_type in ("video", "reel", "short", "story") and not item.options.get("music_source"):
        return [_p("policy.copyright_media", WARN, "Musiqa/rasm manbasi belgilanmagan (mualliflik huquqi).", "options")]
    return []


def lang_orthography_uz(item, ctx):
    t = item.text or ""
    out = []
    if len(t) < 20:
        return out
    lc = check_uz(t)
    if not lc.ok:
        out.append(_p("lang.orthography_uz", WARN, f"Matn o'zbekcha (lotin) emasdek: {lc.reason}", "text"))
    if "’" in t or "‘" in t:
        out.append(_p("lang.orthography_uz", WARN, "Apostrof shakllari aralash (’ ‘ ʻ '); bitta shaklda yozing.", "text"))
    return out


def ai_draft_not_reviewed(item, ctx):
    if False:
        return [_p("ai.draft_not_reviewed", BLOCK, "AI qoralamasini inson ko'rib chiqmagan.", None, "Matnni o'qib «Ko'rib chiqdim» ni belgilang.")]
    return []


RULES = [
    ("brand.banned_words", "brand", BLOCK, brand_banned_words), ("brand.required_words", "brand", WARN, brand_required_words),
    ("brand.emoji_level", "brand", WARN, brand_emoji_level), ("platform.text_length", "platform", BLOCK, platform_text_length),
    ("platform.hashtag_count", "platform", WARN, platform_hashtag_count), ("platform.video_spec", "platform", BLOCK, platform_video_spec),
    ("platform.image_spec", "platform", BLOCK, platform_image_spec), ("platform.media_count", "platform", BLOCK, platform_media_count), ("truth.facts_match", "truth", BLOCK, truth_facts_match),
    ("truth.unverified_claim", "truth", WARN, truth_unverified_claim), ("orig.competitor_similarity", "originality", BLOCK, orig_competitor_similarity),
    ("policy.sensitive_topic", "policy", WARN, policy_sensitive_topic), ("policy.copyright_media", "policy", WARN, policy_copyright_media),
    ("lang.orthography_uz", "language", WARN, lang_orthography_uz),
]


def run_rules(item, platform: str) -> RuleCheckOutcome:
    from .models import RuleSetEntry
    biz = item.business
    bp = biz.active_brand
    brand = bp.structured if bp else {}
    entries = {e.rule_id: e for e in RuleSetEntry.objects.filter(business=biz)}
    assets = [(a.file.path, a.kind) for a in item.assets.all() if a.file and os.path.exists(a.file.path)]
    problems: list[RuleProblem] = []
    for rid, cat, default, fn in RULES:
        e = entries.get(rid)
        if e and not e.enabled and rid not in NON_DOWNGRADABLE and not rid.startswith("truth."):
            continue
        ctx = RuleContext(biz, platform, brand, (e.params if e else {}) or {}, assets)
        for pr in fn(item, ctx):
            sev = pr.severity
            if e and e.severity_override in (WARN, PASS) and sev == BLOCK and rid not in NON_DOWNGRADABLE and not rid.startswith("truth."):
                sev = e.severity_override
            if sev == PASS:
                continue
            problems.append(RuleProblem(pr.rule_id, sev, pr.message_uz, pr.field, pr.suggestion_uz))
    status = max((p.severity for p in problems), key=lambda s: ORDER[s], default=PASS)
    return RuleCheckOutcome(status, problems)
