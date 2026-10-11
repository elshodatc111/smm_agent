"""Biznes pasporti: biznes turiga qarab savollar, to'liqlik foizi va AI uchun ixcham kontekst.
Pasport bo'sh bo'lsa tavsiyalar «ma'lumot yetarli emas» deb belgilanadi."""
from __future__ import annotations

from .models import Business
from .types_data import CORE_KEYS, GENERAL_FIELDS

CORE_LABELS = {
    "industry": "Soha", "region": "Hudud", "description": "Biznes haqida", "products": "Xizmat / mahsulotlar",
    "price_range": "Narx oralig'i", "audience": "Maqsadli auditoriya", "contact_info": "Aloqa ma'lumotlari",
}


def type_fields(business: Business) -> list[dict]:
    t = business.template
    return list(t.profile_fields) if t and t.profile_fields else []


def _val(business: Business, section: str, key: str) -> str:
    return str(((business.profile or {}).get(section) or {}).get(key) or "").strip()


def sections(business: Business) -> list[dict]:
    """[{id, title, fields:[{key,label,kind,help,choices,value,section}]}]"""
    out = []
    core = []
    for k in CORE_KEYS:
        v = str(getattr(business, k, "") or "").strip()
        core.append({"key": k, "label": CORE_LABELS[k], "value": v, "section": "core", "kind": "long" if k in ("description", "products", "audience", "contact_info") else "text", "help": ""})
    out.append({"id": "core", "title": "Asosiy ma'lumotlar", "fields": core})
    tf = type_fields(business)
    if tf:
        out.append({"id": "type", "title": f"{business.template.name}: tur bo'yicha savollar",
                    "fields": [{**f, "value": _val(business, "type", f["key"]), "section": "type"} for f in tf]})
    out.append({"id": "general", "title": "Strategiya va ishonch",
                "fields": [{**f, "value": _val(business, "general", f["key"]), "section": "general"} for f in GENERAL_FIELDS]})
    return out


def completeness(business: Business) -> dict:
    secs = sections(business)
    total = sum(len(s["fields"]) for s in secs)
    filled = sum(1 for s in secs for f in s["fields"] if f["value"])
    per = []
    for s in secs:
        n = len(s["fields"])
        k = sum(1 for f in s["fields"] if f["value"])
        per.append({"id": s["id"], "title": s["title"], "filled": k, "total": n, "pct": round(100 * k / n) if n else 100})
    pct = round(100 * filled / total) if total else 0
    missing = [f["label"] for s in secs for f in s["fields"] if not f["value"]]
    level = "yaxshi" if pct >= 80 else ("o'rtacha" if pct >= 50 else "past")
    return {"pct": pct, "filled": filled, "total": total, "sections": per, "missing": missing, "level": level,
            "ok_for_ai": pct >= 50}


def save_answers(business: Business, data: dict[str, dict[str, str]]) -> None:
    """data = {"core": {...}, "type": {...}, "general": {...}}"""
    for k, v in (data.get("core") or {}).items():
        if k in CORE_KEYS:
            setattr(business, k, (v or "").strip())
    prof = dict(business.profile or {})
    for sec in ("type", "general"):
        if sec in data:
            cur = dict(prof.get(sec) or {})
            cur.update({k: (v or "").strip() for k, v in data[sec].items()})
            prof[sec] = cur
    business.profile = prof
    business.save()


def brief(business: Business, max_chars: int = 2600) -> str:
    """AI uchun ixcham kontekst (pasportdan). Sirlar yo'q — faqat biznes tavsifi."""
    lines = [f"Biznes: {business.name}", f"Turi: {business.template.name if business.template else 'belgilanmagan'}"]
    for s in sections(business):
        for f in s["fields"]:
            if f["value"]:
                lines.append(f"- {f['label']}: {f['value'][:300]}")
    lines.append(f"Asosiy maqsad: {business.get_main_goal_display()}")
    txt = "\n".join(lines)
    return txt[:max_chars]
