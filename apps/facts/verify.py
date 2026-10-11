"""Faktlarni tekshirish (kod): iqtibos manba matnida bormi, raqamlar mosmi, manba darajasi talabi bajarildimi."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

NUM_RE = re.compile(r"\d[\d\s.,]*\d|\d")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w%$€£]+", " ", (s or "").lower())).strip()


def numbers(s: str) -> set[str]:
    out = set()
    for m in NUM_RE.findall(s or ""):
        d = re.sub(r"[^\d]", "", m)
        if d:
            out.add(d.lstrip("0") or "0")
    return out


def quote_in_source(quote: str, source_text: str) -> bool:
    q, s = _norm(quote), _norm(source_text)
    if len(q) < 12:
        return False
    if q in s:
        return True
    # kichik farqlarga (tinish belgilari, qisqartirish) yo'l qo'yamiz
    sm = SequenceMatcher(None, q, s, autojunk=False)
    m = sm.find_longest_match(0, len(q), 0, len(s))
    return m.size >= 0.92 * len(q)


def check_point(claim: str, quote: str, source_title: str, source_snippet: str) -> dict:
    """Bitta fikrni tekshiradi. claim — o'zbekcha, quote — manbadan aynan olingan parcha."""
    src = f"{source_title}. {source_snippet}"
    found = quote_in_source(quote, src)
    claim_nums = numbers(claim)
    src_nums = numbers(src)
    nums_ok = claim_nums.issubset(src_nums) if claim_nums else True
    return {"quote_found": found, "numbers_ok": nums_ok, "has_numbers": bool(claim_nums), "verified": bool(found and nums_ok)}


STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "is", "are", "with", "by", "at", "as", "from", "that", "this", "it", "its", "be", "will", "new"}


def significant_words(title: str) -> set[str]:
    return {w for w in _norm(title).split() if len(w) > 3 and w not in STOP}


def corroborated(item, claim_nums: set[str], days: int = 30) -> bool:
    """Raqam boshqa (boshqa manbadagi) materialda ham uchrasa va mavzu mos bo'lsa — tasdiqlangan hisoblanadi."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import FactItem
    if not claim_nums:
        return True
    base = significant_words(item.title)
    since = timezone.now() - timedelta(days=days)
    for other in FactItem.objects.filter(fetched_at__gte=since).exclude(source_id=item.source_id).select_related("source")[:400]:
        txt = f"{other.title}. {other.snippet}"
        if claim_nums.issubset(numbers(txt)) and len(base & significant_words(other.title + " " + other.snippet[:200])) >= 2:
            return True
    return False
