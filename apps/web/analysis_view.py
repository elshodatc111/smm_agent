"""Media va ssenariy tahlilini «bir qarashda» tushunarli kartaga aylantiradi (eski va yangi AI formatlarini qabul qiladi)."""
from __future__ import annotations

VERDICTS = {
    "chiqarish": ("✅ Chiqarish mumkin", "ok", "Fayl tayyor — asosiy muammo yo'q."),
    "tuzatish": ("🛠 Tuzatib chiqaring", "warn", "G'oya yaxshi, lekin quyidagi tuzatishlar natijani oshiradi."),
    "qayta_tayyorlash": ("⛔ Qayta tayyorlash kerak", "bad", "Hozirgi holida kutilgan natijani bermaydi."),
}
SCORE_LABELS = [("hook", "Hook (boshlanish)"), ("visual", "Vizual sifat"), ("pacing", "Sur'at"), ("audio_text", "Ovoz / matn"), ("cta", "CTA (chaqiriq)"), ("brand_fit", "Brendga mosligi")]
PLAT_LABELS = {"instagram_reels": "Instagram Reels", "shorts": "YouTube Shorts", "telegram": "Telegram", "instagram_feed": "Instagram lenta", "youtube": "YouTube"}
PRIO = {"yuqori": ("Muhim", "bad"), "o'rta": ("O'rta", "warn"), "past": ("Past", "")}


def _n(v, hi=10):
    try:
        return max(0, min(hi, float(v)))
    except (TypeError, ValueError):
        return None


def _cls(v, hi=10):
    r = v / hi
    return "ok" if r >= .7 else "warn" if r >= .45 else "bad"


def normalize_media(ai: dict | None) -> dict | None:
    if not isinstance(ai, dict) or not ai:
        return None
    sc = dict(ai.get("scores") or {})
    sc.setdefault("hook", (ai.get("hook") or {}).get("strength"))
    sc.setdefault("visual", ai.get("visual_quality"))
    sc.setdefault("cta", (ai.get("cta") or {}).get("clarity"))
    sc.setdefault("brand_fit", ai.get("brand_fit"))
    scores = []
    for k, lbl in SCORE_LABELS:
        v = _n(sc.get(k))
        if v is not None:
            scores.append({"label": lbl, "v": round(v, 1), "pct": int(v * 10), "cls": _cls(v)})
    vals = [x["v"] for x in scores]
    total = _n(ai.get("score"), 100)
    if total is None and vals:
        total = round(sum(vals) / len(vals) * 10)
    vk = ai.get("verdict") if ai.get("verdict") in VERDICTS else None
    if vk is None and total is not None:
        vk = "chiqarish" if total >= 72 else "tuzatish" if total >= 45 else "qayta_tayyorlash"
    verdict = None
    if vk:
        t, c, d = VERDICTS[vk]
        verdict = {"title": t, "cls": c, "text": ai.get("verdict_reason") or d}
    scenes = []
    for s in (ai.get("scenes") or [])[:14]:
        if isinstance(s, dict):
            a = _n(s.get("attention")) or 0
            scenes.append({"t": s.get("t", ""), "what": s.get("what", ""), "note": s.get("note", ""), "att": a, "h": 12 + int(a * 8), "cls": _cls(a)})
    fit = []
    for k, v in (ai.get("platform_fit") or {}).items():
        x = _n(v)
        if x is not None:
            fit.append({"label": PLAT_LABELS.get(k, k), "v": round(x, 1), "cls": _cls(x)})
    imps = []
    for i in ai.get("improvements") or []:
        if isinstance(i, dict):
            lbl, cl = PRIO.get(str(i.get("priority", "")).lower(), ("", ""))
            imps.append({"fix": i.get("fix") or i.get("text") or "", "prio": lbl, "cls": cl})
        elif i:
            imps.append({"fix": str(i), "prio": "", "cls": ""})
    hook = ai.get("hook") if isinstance(ai.get("hook"), dict) else {}
    cta = ai.get("cta") if isinstance(ai.get("cta"), dict) else {}
    return {"total": int(total) if total is not None else None, "total_cls": _cls(total, 100) if total is not None else "", "verdict": verdict, "scores": scores,
            "scenes": scenes, "fit": fit, "strengths": [str(x) for x in ai.get("strengths") or []], "improvements": imps,
            "hook_text": hook.get("text", ""), "cta_text": cta.get("text", "") or ("bor" if cta.get("present") else "yo'q"), "cta_present": bool(cta.get("present")),
            "pacing": ai.get("pacing") if isinstance(ai.get("pacing"), str) else "", "summary": ai.get("summary", "")}


def normalize_script(an) -> dict | None:
    d = an.data if an and isinstance(an.data, dict) else None
    if not d:
        return None
    names = {"hook": "Hook", "structure": "Tuzilma", "pace": "Sur'at", "duration_fit": "Davomiylik", "cta": "CTA", "brand_fit": "Brendga mosligi", "sales": "Sotuv kuchi"}
    crit = []
    for k, lbl in names.items():
        v = _n((d.get("criteria") or {}).get(k))
        if v is not None:
            crit.append({"label": lbl, "v": round(v, 1), "pct": int(v * 10), "cls": _cls(v)})
    return {"total": an.score, "total_cls": _cls(an.score, 100), "scores": crit, "fixes": [str(x) for x in d.get("fixes") or []]}
