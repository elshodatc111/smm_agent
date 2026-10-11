"""Faktlar/yangiliklar: yig'ish → mos materialni tanlash → AI taklif (post YOZMAYDI) → kod tekshiruvi → saqlash."""
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from difflib import SequenceMatcher

from django.utils import timezone

from apps.core.settings_store import get_setting

from . import fetcher, verify
from .models import FactItem, FactSource, FactSuggestion, FactTopic
from .sources_data import SOURCES, domains_for

log = logging.getLogger(__name__)
KIND_UZ = dict(FactTopic.KIND)
FORMATS = {"telegram": ["Oddiy post", "Rasm + qisqa matn", "So'rovnoma", "Karusel (fayl)"], "instagram": ["Karusel", "Reels", "Bitta rasm + izoh", "Stories"]}


# ------------------------------------------------------------------ manbalar
def ensure_sources() -> int:
    n = 0
    for name, url, feed, tier, lang, doms in SOURCES:
        _, created = FactSource.objects.get_or_create(feed_url=feed, defaults={"name": name, "url": url, "tier": tier, "language": lang, "domains": doms, "is_system": True})
        n += created
    return n


def business_domains(business) -> list[str]:
    t = business.template
    base = list(domains_for(t.key if t else None))
    extra = (t.config or {}).get("domains") if t else None
    for d in extra or []:
        if d not in base:
            base.append(d)
    return base


def sources_for(business):
    doms = set(business_domains(business))
    out = []
    for s in FactSource.objects.filter(is_active=True):
        if s.is_system:
            if doms & set(s.domains or []):
                out.append(s)
        else:   # foydalanuvchi qo'shgan manba: sohalar bo'sh bo'lsa hamma biznesga mos
            if not s.domains or doms & set(s.domains):
                out.append(s)
    return out


def refresh_source(src: FactSource) -> dict:
    now = timezone.now()
    try:
        entries = fetcher.fetch(src.feed_url)
    except fetcher.FeedError as e:
        src.last_checked_at, src.last_ok, src.last_error = now, False, str(e)[:290]
        src.save(update_fields=["last_checked_at", "last_ok", "last_error"])
        return {"ok": False, "new": 0, "error": str(e)}
    new = 0
    for e in entries:
        _, created = FactItem.objects.get_or_create(url=e["url"][:600], defaults={"source": src, "title": e["title"][:400], "published_at": e["published_at"], "snippet": e["snippet"]})
        new += created
    src.last_checked_at, src.last_ok, src.last_error = now, True, ""
    src.save(update_fields=["last_checked_at", "last_ok", "last_error"])
    return {"ok": True, "new": new, "error": ""}


# ------------------------------------------------------------------ mavzular
def ensure_default_topics(business) -> int:
    """Biznes turi mavzulari asosida har tarmoq uchun bitta boshlang'ich yo'nalish yaratadi (bo'lmasa)."""
    if business.fact_topics.exists():
        return 0
    kws = list(business.template.topics) if business.template and business.template.topics else []
    plats = sorted({a.platform for a in business.accounts.filter(archived_at__isnull=True) if a.platform in ("telegram", "instagram")})
    n = 0
    for pl in plats:
        FactTopic.objects.create(business=business, platform=pl, title="Soha yangiliklari va foydali ma'lumotlar", keywords=kws, kinds=["fact", "news", "tip"])
        n += 1
    return n


# ------------------------------------------------------------------ taklif
def _relevant_items(business, topic: FactTopic, limit: int = 8):
    max_age = int(get_setting("facts.max_age_days", 21))
    since = timezone.now() - timedelta(days=max_age)
    src_ids = [s.pk for s in sources_for(business)]
    kws = [k.lower() for k in (topic.keywords or []) if k]
    used_urls = set()
    for sg in FactSuggestion.objects.filter(business=business, platform=topic.platform).exclude(status="dismissed"):
        for p in sg.key_points or []:
            used_urls.add(p.get("url"))
    scored = []
    qs = FactItem.objects.filter(source_id__in=src_ids).select_related("source").order_by("-published_at", "-fetched_at")[:400]
    for it in qs:
        if (it.published_at or it.fetched_at) < since or it.url in used_urls:
            continue
        txt = f"{it.title} {it.snippet}".lower()
        hits = sum(1 for k in kws if k in txt)
        words = sum(1 for k in kws for w in k.split() if len(w) > 3 and w in txt)
        score = hits * 3 + words + (1.5 if it.source.tier == "A" else 0)
        if kws and score <= 0:
            continue
        scored.append((score, it))
    scored.sort(key=lambda t: (-t[0], -(t[1].published_at or t[1].fetched_at).timestamp()))
    return [it for _, it in scored[:limit]]


def _similar_title(business, title: str) -> bool:
    t = re.sub(r"\W+", " ", title.lower())
    for old in FactSuggestion.objects.filter(business=business, created_at__gte=timezone.now() - timedelta(days=45)).values_list("title", flat=True):
        if SequenceMatcher(None, t, re.sub(r"\W+", " ", old.lower())).ratio() > 0.8:
            return True
    return False


def _prompt(business, topic, items) -> str:
    from apps.businesses.passport import brief
    its = [{"id": it.pk, "manba": it.source.name, "daraja": it.source.tier, "sarlavha": it.title, "parcha": it.snippet[:600]} for it in items]
    kinds = ", ".join(KIND_UZ.get(k, k) for k in (topic.kinds or ["fact", "news", "tip"]))
    return (
        "Sen SMM kontent strategisan. Quyida tasdiqlangan manbalardan olingan materiallar bor. Vazifa: shu materiallardan biznes uchun foydali POST G'OYALARI taklif qilish. "
        "TAYYOR POST MATNINI YOZMA. Faqat: mavzu, qanday burchakdan yondashish, nega bu biznes uchun muhim, mos format va manbadan olingan asosiy fikrlar.\n"
        "QOIDALAR: 1) Faqat o'zbek tilida (lotin) yoz, manba inglizcha bo'lsa tarjima qil. 2) Har asosiy fikr uchun materialning 'id'sini va manbadagi AYNAN OLINGAN iqtibosni (asl tilda) ko'rsat. "
        "3) Yangi raqam, nom yoki da'vo qo'shma: fikrdagi har raqam iqtibosda bo'lishi shart. 4) Materialda yo'q narsani to'qima. 5) Eng ko'pi bilan 3 ta taklif; mos kelmasa bo'sh ro'yxat qaytar.\n"
        f"Platforma: {topic.platform}. Yo'nalish: {topic.title}. Turlari: {kinds}.\nBiznes pasporti:\n{brief(business, 1500)}\n"
        f"Materiallar: {json.dumps(its, ensure_ascii=False)}\n"
        'Faqat JSON: {"suggestions":[{"kind":"fact|news|tip","title":"","angle":"","why":"","format":"","points":[{"claim":"o\'zbekcha fikr","item_id":0,"quote":"manbadan aynan"}]}]}')


def _verify_points(points: list[dict], items_by_id: dict) -> tuple[list[dict], int]:
    kept, dropped = [], 0
    for p in points or []:
        if not isinstance(p, dict):
            continue
        it = items_by_id.get(p.get("item_id"))
        claim, quote = str(p.get("claim", "")).strip(), str(p.get("quote", "")).strip()
        if not it or not claim:
            dropped += 1
            continue
        chk = verify.check_point(claim, quote, it.title, it.snippet)
        ok = chk["verified"]
        if ok and chk["has_numbers"] and it.source.tier != "A" and not verify.corroborated(it, verify.numbers(claim)):
            ok = False   # raqamli fikr: A manba yoki ikkinchi mustaqil manba kerak
        if not ok:
            dropped += 1
            continue
        kept.append({"claim": claim[:400], "quote": quote[:400], "item_id": it.pk, "source": it.source.name, "tier": it.source.tier, "url": it.url,
                     "date": it.published_at.date().isoformat() if it.published_at else "", "verified": True, "has_numbers": chk["has_numbers"]})
    return kept, dropped


def generate_for_topic(topic: FactTopic, user=None, router=None, use_ai: bool = True, max_new: int | None = None) -> int:
    business = topic.business
    items = _relevant_items(business, topic)
    if not items:
        return 0
    max_new = max_new or int(get_setting("facts.per_topic_per_day", 2))
    created = 0
    by_id = {it.pk: it for it in items}
    suggestions = []
    by_ai = False
    if use_ai:
        try:
            from apps.ai_router.router import generate
            from apps.ai_router.types import TaskType
            res, _ = generate(TaskType.LONG_UZ, _prompt(business, topic, items), business=business, kind="facts_suggest", user=user, schema={"json": True}, router=router)
            data = res.data if isinstance(res.data, dict) else {}
            suggestions = [s for s in (data.get("suggestions") or []) if isinstance(s, dict)]
            by_ai = True
        except Exception as e:  # noqa: BLE001 — AI bo'lmasa tarjimasiz zaxira taklif beriladi
            log.warning("facts AI failed: %s", e)
    if not suggestions and get_setting("facts.allow_untranslated", True):
        for it in items[:max_new]:
            suggestions.append({"kind": "news", "title": it.title, "angle": "Manba sarlavhasi asl tilda (tarjima qilinmagan). Avval mazmunini o'qib chiqing.",
                                "why": "AI tarjimasi hozir mavjud emas: sozlamalarda AI kalitini tekshiring.", "format": "",
                                "points": [{"claim": it.title, "item_id": it.pk, "quote": it.snippet[:240] or it.title}]})
        by_ai = False
    for s in suggestions:
        if created >= max_new:
            break
        title = str(s.get("title", "")).strip()[:300]
        if not title or _similar_title(business, title):
            continue
        kept, dropped = _verify_points(s.get("points") or [], by_id)
        if not kept:
            continue
        kind = s.get("kind") if s.get("kind") in KIND_UZ else "fact"
        FactSuggestion.objects.create(business=business, topic=topic, platform=topic.platform, kind=kind, title=title, angle=str(s.get("angle", ""))[:800], why=str(s.get("why", ""))[:800],
                                      format=str(s.get("format", ""))[:40], key_points=kept, verified_count=len(kept), by_ai=by_ai)
        created += 1
    return created


def refresh_all(business=None, user=None, router=None, fetch: bool = True) -> dict:
    """Manbalarni yangilaydi va har faol mavzu uchun takliflar yaratadi."""
    from apps.businesses.models import Business
    ensure_sources()
    biz = [business] if business else list(Business.objects.filter(archived_at__isnull=True))
    fetched = new_items = errors = 0
    if fetch:
        seen = set()
        cap = int(get_setting("facts.sources_per_run", 25))
        for b in biz:
            for s in sources_for(b):
                if s.pk in seen or len(seen) >= cap:
                    continue
                seen.add(s.pk)
                r = refresh_source(s)
                fetched += 1
                new_items += r["new"]
                errors += 0 if r["ok"] else 1
    created = 0
    per: dict[int, int] = {}
    for b in biz:
        ensure_default_topics(b)
        n = 0
        for t in b.fact_topics.filter(active=True):
            n += generate_for_topic(t, user=user, router=router)
        per[b.pk] = n
        created += n
    return {"sources": fetched, "new_items": new_items, "errors": errors, "suggestions": created, "per_business": per}
