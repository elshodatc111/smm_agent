"""Reklama taklifi: maqsadga mos ballash (kod) + tushuntirish (AI, zaxirada qoidalar). Byudjet yo'q, reklama yoqilmaydi.
Raqamlarni KOD hisoblaydi; AI faqat tahlil matni, auditoriya g'oyalari va sinov rejasini taklif qiladi (post matnini yozmaydi)."""
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

from django.utils import timezone

from apps.core.settings_store import get_setting

from .models import AdProposal

log = logging.getLogger(__name__)

OBJ_LABEL = dict(AdProposal.OBJECTIVES)
VIDEO_TYPES = {"reel", "video", "short", "clip", "reels"}
PLAT_AD = {"telegram": "Telegram Ads", "instagram": "Instagram (Boost)"}

# Maqsadga qarab komponent vaznlari. Komponentlar: eng(ER) share save convo reach ret click offer rec
WEIGHTS = {
    "subscribers": {"share": .28, "reach": .22, "eng": .20, "save": .12, "convo": .04, "rec": .14},
    "views": {"ret": .32, "reach": .26, "share": .14, "eng": .14, "rec": .14},
    "leads": {"convo": .26, "save": .16, "eng": .16, "click": .14, "offer": .16, "share": .04, "rec": .08},
    "sales": {"offer": .24, "convo": .20, "save": .20, "eng": .12, "click": .14, "ret": .04, "rec": .06},
    "profile": {"reach": .24, "ret": .22, "eng": .18, "share": .10, "save": .12, "rec": .14},
}
COMP_UZ = {"eng": "faollik (ER)", "share": "ulashishlar", "save": "saqlashlar", "convo": "izohlar", "reach": "qamrov", "ret": "ushlab turish",
           "click": "havola bosish", "offer": "taklif/CTA belgilari", "rec": "yangilik"}
OFFER_RE = re.compile(r"(narx|so['’ʻ]?m|aksiya|chegirma|buyurtma|yoz(il|ing)|ro['’ʻ]?yxat|xizmat|aloqa|bog['’ʻ]?lan|kurs|sotib|qabul|@|t\.me/|https?://|\+998)", re.I)


def prank(values: list[float], x: float) -> float:
    """Foizli o'rin (0..1): barqaror va kichik tanlanmada ham ma'noli."""
    vs = [v for v in values if v is not None]
    if len(vs) < 2:
        return 0.5
    lower = sum(1 for v in vs if v < x)
    equal = sum(1 for v in vs if v == x)
    return (lower + 0.5 * equal) / len(vs)


def _components(r, followers: int | None) -> dict[str, float | None]:
    reach = r.reach or r.views
    views = r.views
    c: dict[str, float | None] = {}
    c["eng"] = r.er if r.er is not None else None
    c["share"] = ((r.shares or 0) / reach) if reach else None
    c["save"] = ((r.saves or 0) / reach) if reach else None
    c["convo"] = ((r.comments or 0) / reach) if reach else None
    base = followers or None
    c["reach"] = (reach / base) if (reach and base) else (float(reach) if reach else None)
    dur = getattr(r.post, "duration_sec", None)
    if r.avg_view_duration_sec and dur:
        c["ret"] = min(1.0, r.avg_view_duration_sec / dur)
    elif r.watch_time_sec and views:
        c["ret"] = r.watch_time_sec / views
    else:
        c["ret"] = None
    c["click"] = r.ctr if r.ctr is not None else None
    text = r.post.text or ""
    c["offer"] = 1.0 if OFFER_RE.search(text) else 0.0
    age_d = (timezone.now() - r.post.published_at).days
    c["rec"] = max(0.0, 1 - age_d / 60)
    return c


def score_candidates(business, account, objective: str, limit: int = 5) -> dict:
    """Akkauntdagi postlarni maqsadga mos balllaydi. Qaytaradi: {picks, stats, notes}."""
    from apps.metrics.analytics import latest_metrics_qs
    from apps.metrics.models import AccountMetrics
    now = timezone.now()
    min_age = float(get_setting("ads.min_age_hours", 24))
    rows = [r for r in latest_metrics_qs(account_id=account.pk, since=now - timedelta(days=75))
            if (now - r.post.published_at).total_seconds() / 3600 >= min_age]
    notes: list[str] = []
    total_rows = len(rows)
    if account.platform == "instagram":
        vid = [r for r in rows if (r.post.media_type or "").lower() in VIDEO_TYPES]
        if vid:
            rows = vid
        elif rows:
            notes.append("Instagramda video/reels topilmadi: barcha postlar ko'rib chiqildi. Boost uchun video tavsiya etiladi.")
    am = AccountMetrics.objects.filter(account=account, followers__isnull=False).order_by("-taken_at").first()
    followers = int(am.followers) if am else None
    stats = {"posts_total": total_rows, "posts_used": len(rows), "followers": followers, "min_age_hours": min_age}
    if not rows:
        return {"picks": [], "stats": stats, "notes": notes + ["Baholash uchun yetarli yoshdagi post topilmadi."]}
    comps = [(_components(r, followers), r) for r in rows]
    w = WEIGHTS[objective]
    pools = {k: [c[k] for c, _ in comps if c[k] is not None] for k in w}
    med_views = sorted([r.views or 0 for r in rows])[len(rows) // 2]
    out = []
    for c, r in comps:
        used_w = 0.0
        s = 0.0
        parts = []
        for k, wt in w.items():
            v = c.get(k)
            if v is None:
                continue
            pr = prank(pools[k], v) if k != "offer" else v
            s += wt * pr
            used_w += wt
            parts.append((k, pr, wt))
        score = (s / used_w) if used_w else 0.0
        cover = used_w / sum(w.values())
        parts.sort(key=lambda t: -(t[1] * t[2]))
        strong = [f"{COMP_UZ[k]} yuqori" for k, pr, wt in parts if pr >= 0.7][:3]
        weak = [COMP_UZ[k] for k, pr, wt in parts if pr <= 0.3][:2]
        out.append({"post_id": r.post_id, "score": round(score * 100, 1), "coverage": round(cover, 2), "views": r.views, "reach": r.reach, "likes": r.likes,
                    "comments": r.comments, "shares": r.shares, "saves": r.saves, "er": r.er, "media_type": r.post.media_type, "url": r.post.url,
                    "published_at": r.post.published_at.isoformat(), "age_days": (now - r.post.published_at).days,
                    "title": (r.post.text or "").strip().split("\n")[0][:110] or "(matnsiz post)", "strong": strong, "weak": weak,
                    "vs_median_views": round((r.views or 0) / med_views, 2) if med_views else None, "has_offer": bool(c.get("offer"))})
    out.sort(key=lambda d: -d["score"])
    stats["median_views"] = med_views
    return {"picks": out[:limit], "stats": stats, "notes": notes}


def confidence_of(stats: dict, picks: list[dict]) -> tuple[str, list[str]]:
    why = []
    n = stats.get("posts_used", 0)
    f = stats.get("followers")
    if n >= 12:
        lvl = 2
    elif n >= 5:
        lvl = 1
    else:
        lvl = 0
        why.append(f"Baholash uchun faqat {n} ta post bor (kamida 5–12 ta kerak).")
    if f is not None and f < 100:
        lvl = min(lvl, 1)
        why.append(f"Auditoriya kichik ({f} ta): ko'rsatkichlar tasodifiy tebranishi mumkin.")
    if picks and picks[0].get("coverage", 1) < 0.6:
        lvl = min(lvl, 1)
        why.append("Ba'zi metrikalar (ulashish/saqlash/ushlab turish) yig'ilmagan: baho qisman.")
    return ["low", "medium", "high"][lvl], why


def _verdict(picks: list[dict], stats: dict) -> tuple[str, str]:
    if not picks:
        return "wait", "Hozircha reklama uchun nomzod yo'q: ma'lumot yetarli emas."
    top = picks[0]
    vm = top.get("vs_median_views")
    if top["score"] < 55 or (vm is not None and vm < 1.1):
        return "improve_first", "Hech bir post o'rtacha darajadan sezilarli yuqori emas: avval kontent sifatini oshirib, so'ng reklamani sinab ko'rish maqbul."
    return "advertise", "Quyidagi post(lar) organik ko'rsatkichlari bo'yicha reklama uchun eng yaxshi nomzod."


def _platform_goal(platform: str, objective: str) -> dict:
    if platform == "telegram":
        m = {"subscribers": ("Kanalga obunachi jalb qilish (kanal reklamasi)", "Reklama kanal havolasiga olib borilsa, to'g'ridan-to'g'ri obuna beradi."),
             "views": ("Postni ko'proq odamga ko'rsatish (post reklamasi)", "Belgilangan postning ko'rishlarini oshirish uchun post havolasi bilan reklama beriladi."),
             "leads": ("Murojaat: postdagi aloqa/havola orqali", "Postda aniq CTA va aloqa bo'lishi shart: reklama shu postga olib boradi."),
             "sales": ("Sotuv: taklifli postga yo'naltirish", "Narx/taklif aniq aytilgan postni tanlang va havolani qisqa havola (UTM) bilan o'lchang."),
             "profile": ("Kanalni tanishtirish", "Yangi auditoriyaga kanal haqida tasavvur beradigan post/kanal havolasi.")}
    else:
        m = {"subscribers": ("Boost → Profil tashriflari (Profile visits)", "Boost qilingan reels yangi odamlarni profilga olib keladi; profil to'liq bo'lishi kerak."),
             "views": ("Boost → Ko'rishlar/Qamrov", "Videoni ko'proq odamga ko'rsatish. Qisqa, ushlab turuvchi videoni tanlang."),
             "leads": ("Boost → Xabarlar yoki sayt tashriflari", "Video oxirida aniq CTA (Direct yoki havola) bo'lishi kerak."),
             "sales": ("Boost → Xabarlar / sayt tashriflari", "Taklif va narx aniq ko'rsatilgan videoni tanlang."),
             "profile": ("Boost → Profil tashriflari", "Profil bio va highlight tayyor bo'lsin.")}
    name, why = m[objective]
    return {"name": name, "why": why}


def _audience_rules(business, platform: str, objective: str) -> dict:
    aud = (business.audience or "").strip()
    regions = [x.strip() for x in re.split(r"[;,]", business.region or "") if x.strip()][:4]
    inst = {
        "summary": aud[:240] or "Maqsadli auditoriya pasportda belgilanmagan: avval «Biznes pasporti»ni to'ldiring.",
        "regions": regions or ["O'zbekiston (kerak bo'lsa shahar bo'yicha torayting)"],
        "age": "Pasportdagi auditoriya yoshiga mos (taxminan 18–45 dan boshlab, keyin natijaga qarab toraytiring)",
        "interests": [],
        "channels_topics": [],
    }
    if platform == "telegram":
        inst["channels_topics"] = ["Biznes sohangizga yaqin Telegram kanallar va mavzular", "Shu soha raqobatchilari/hamkorlari kanallari (agar reklama qabul qilsa)"]
        inst["note"] = "Telegram Ads auditoriyani kanal, mavzu va til bo'yicha tanlaydi."
    else:
        inst["note"] = "Instagram Boost'da avval «Avtomatik» auditoriyani, keyin joylashuv/yosh/qiziqish bo'yicha qo'lda sinab ko'ring."
    return inst


def rules_proposal(business, account, objective: str, scored: dict, note: str = "") -> dict:
    picks = scored["picks"]
    verdict, summary = _verdict(picks, scored["stats"])
    plat = account.platform
    creative: list[str] = []
    out_picks = []
    for i, p in enumerate(picks[:3], 1):
        improve = []
        if objective in ("leads", "sales") and not p["has_offer"]:
            improve.append("Postda aniq taklif/aloqa (CTA) yo'q: reklamadan oldin CTA qo'shilgan variantni ham sinab ko'ring.")
        if "ushlab turish" in " ".join(p["weak"]) and plat == "instagram":
            improve.append("Ushlab turish past: videoning birinchi 3 soniyasini kuchaytiring.")
        if "ulashishlar" in " ".join(p["weak"]):
            improve.append("Ulashish past: foydali yoki hayratlantiruvchi fikrni ko'proq oldinga chiqaring.")
        out_picks.append({"rank": i, "post_id": p["post_id"], "title": p["title"], "url": p["url"], "score": p["score"],
                          "why": p["strong"] or ["boshqa postlardan yaxshiroq umumiy ko'rsatkich"], "improve": improve,
                          "directions": []})
    if plat == "telegram" and objective == "subscribers":
        creative.append("Reklama matni kanal foydasini bir jumlada aytsin (kim uchun va nima oladi). Matnni o'zingiz yozing: tizim faqat yo'nalish beradi.")
    if objective in ("leads", "sales"):
        creative.append("Reklama yetib borgach odam nima qilishi aniq bo'lsin: bitta havola yoki bitta tugma. Qisqa havolada UTM belgisi qo'ying (Havolalar bo'limi).")
    if not creative:
        creative.append("Bitta reklamada bitta xabar: ko'p narsani aytmang.")
    test = {
        "duration_days": 5 if plat == "telegram" else 4,
        "variants": ["1-variant: eng yuqori ballli post", "2-variant: ikkinchi post yoki boshqa auditoriya (faqat bitta narsani o'zgartiring)"] if len(picks) > 1 else ["Faqat bitta nomzod bor: sinov uchun auditoriyani o'zgartiring"],
        "success_signals": [{"subscribers": "Obuna narxi o'rtachadan past, obunadan chiqish kam", "views": "Ko'rish narxi pastligi va to'liq ko'rish ulushi yuqoriligi",
                             "leads": "Murojaat soni va sifati, bir murojaat narxi", "sales": "Murojaatdan sotuvga o'tish va sotuv narxi",
                             "profile": "Profil tashrifi narxi pastligi va tashrifdan keyingi obunalar"}[objective]],
        "stop_signals": ["Natija 2 kun ketma-ket o'rtachadan sezilarli yomon bo'lsa to'xtating", "Izohlarda salbiy fikrlar ko'paysa to'xtating"],
    }
    avoid = ["Bir vaqtda ko'p post/auditoriyani sinamang: qaysi biri ishlaganini ajrata olmaysiz.",
             "Natijani 1 kunda baholamang: kamida 3–5 kun kuzating."]
    if scored["stats"].get("followers") is not None and scored["stats"]["followers"] < 100:
        avoid.append("Auditoriya hozircha kichik: reklamadan oldin profil/kanal tavsifi, mahkamlangan post va portfolio tayyor bo'lsin.")
    return {"verdict": verdict, "summary": summary, "objective_label": OBJ_LABEL[objective], "platform_goal": _platform_goal(plat, objective),
            "picks": out_picks, "audience": _audience_rules(business, plat, objective), "creative_notes": creative, "test_plan": test, "avoid": avoid,
            "guide_key": f"{plat}_{objective}"}


AI_SCHEMA_HINT = ('{"summary":"2-3 gap","audience":{"summary":"","age":"","regions":[],"interests":[],"channels_topics":[]},'
                  '"picks":[{"post_id":0,"directions":["reklama xabari yo\'nalishi (tayyor matn EMAS)"],"improve":["nimani yaxshilash"]}],'
                  '"creative_notes":[""],"test_plan":{"duration_days":0,"variants":[""],"success_signals":[""],"stop_signals":[""]},"avoid":[""]}')


def _ai_enrich(business, account, objective: str, base: dict, scored: dict, note: str, user=None, router=None) -> dict | None:
    from apps.ai_router.router import generate
    from apps.ai_router.types import TaskType
    from apps.businesses.passport import brief
    compact = [{"post_id": p["post_id"], "sarlavha": p["title"], "ball": p["score"], "kuchli": p["strong"], "zaif": p["weak"], "ko'rish": p["views"],
                "ER": p["er"], "taklif_bor": p["has_offer"]} for p in scored["picks"][:3]]
    prompt = (
        "Sen tajribali SMM-strateg va targetologsan. Quyida biznes pasporti va KOD hisoblagan raqamlar. Reklama KAMPANIYASINI sen yoqmaysan: "
        "targetolog yoqadi. Sening vazifang: qaysi postga nima uchun reklama qilish, auditoriya, nimani yaxshilash va sinov rejasi bo'yicha TAKLIF berish.\n"
        "QOIDALAR: faqat o'zbek (lotin); tayyor post yoki reklama matnini YOZMA, faqat xabar yo'nalishlarini ber; raqamlarni o'ylab topma va o'zgartirma; "
        "byudjet/so'm summa yozma; pasportda yo'q narsani to'qima.\n"
        f"Platforma: {PLAT_AD[account.platform]}. Reklama maqsadi: {OBJ_LABEL[objective]}. Foydalanuvchi izohi: {note or '—'}\n"
        f"Biznes pasporti:\n{brief(business, 1800)}\n"
        f"Nomzodlar (kod hisoblagan): {json.dumps(compact, ensure_ascii=False)}\n"
        f"Holat: {base['verdict']} — {base['summary']}\n"
        f"Faqat JSON qaytar: {AI_SCHEMA_HINT}")
    res, gen = generate(TaskType.AD_PLAN, prompt, business=business, kind="ad_proposal", user=user, schema={"json": True}, router=router)
    d = res.data if isinstance(res.data, dict) else None
    return d


def _s(v, n=300) -> str:
    return str(v).strip()[:n] if v is not None else ""


def _list(v, n=6, m=240):
    if isinstance(v, str):
        v = [v]
    return [_s(x, m) for x in (v or []) if _s(x, m)][:n]


def merge_ai(base: dict, ai: dict) -> dict:
    """AI javobini tekshirib, faqat ruxsat etilgan maydonlarni qo'shadi; raqamlar va postlar koddan."""
    out = json.loads(json.dumps(base))
    if _s(ai.get("summary")):
        out["summary"] = _s(ai["summary"], 500)
    a = ai.get("audience") if isinstance(ai.get("audience"), dict) else {}
    for k in ("summary", "age"):
        if _s(a.get(k)):
            out["audience"][k] = _s(a[k], 300)
    for k in ("regions", "interests", "channels_topics"):
        if _list(a.get(k)):
            out["audience"][k] = _list(a.get(k))
    byid = {p["post_id"]: p for p in out["picks"]}
    for ap in (ai.get("picks") or []):
        if isinstance(ap, dict) and ap.get("post_id") in byid:
            tgt = byid[ap["post_id"]]
            if _list(ap.get("directions"), 4):
                tgt["directions"] = _list(ap["directions"], 4)
            imp = _list(ap.get("improve"), 4)
            if imp:
                tgt["improve"] = (tgt.get("improve") or []) + [x for x in imp if x not in (tgt.get("improve") or [])]
    if _list(ai.get("creative_notes")):
        out["creative_notes"] = _list(ai["creative_notes"])
    tp = ai.get("test_plan") if isinstance(ai.get("test_plan"), dict) else {}
    try:
        d = int(tp.get("duration_days"))
        if 2 <= d <= 14:
            out["test_plan"]["duration_days"] = d
    except (TypeError, ValueError):
        pass
    for k in ("variants", "success_signals", "stop_signals"):
        if _list(tp.get(k)):
            out["test_plan"][k] = _list(tp[k])
    if _list(ai.get("avoid")):
        out["avoid"] = _list(ai["avoid"])
    return out


def create_proposal(business, account, objective: str, note: str = "", user=None, router=None, use_ai: bool = True) -> AdProposal:
    if objective not in WEIGHTS:
        raise ValueError("Noma'lum maqsad")
    if account.platform not in PLAT_AD:
        raise ValueError("Reklama taklifi faqat Telegram va Instagram uchun")
    scored = score_candidates(business, account, objective)
    conf, conf_why = confidence_of(scored["stats"], scored["picks"])
    base = rules_proposal(business, account, objective, scored, note)
    result, source = base, "rules"
    if use_ai and scored["picks"]:
        try:
            ai = _ai_enrich(business, account, objective, base, scored, note, user=user, router=router)
            if ai:
                result, source = merge_ai(base, ai), "ai"
        except Exception as e:  # noqa: BLE001 — AI bo'lmasa ham qoidalar bo'yicha taklif beriladi
            log.warning("ads proposal AI failed: %s", e)
            conf_why.append("AI hozir javob bermadi: taklif qoidalar asosida tuzildi.")
    from apps.businesses.passport import completeness
    comp = completeness(business)
    if not comp["ok_for_ai"]:
        conf_why.append(f"Biznes pasporti {comp['pct']}% to'ldirilgan: auditoriya va xabar yo'nalishlari taxminiy.")
        conf = "low" if conf == "medium" and comp["pct"] < 30 else conf
    evidence = {"stats": scored["stats"], "notes": scored["notes"], "candidates": scored["picks"], "confidence_reasons": conf_why,
                "passport_pct": comp["pct"], "weights": WEIGHTS[objective]}
    last = AdProposal.objects.filter(business=business, account=account, objective=objective).order_by("-version").first()
    return AdProposal.objects.create(business=business, account=account, platform=account.platform, objective=objective, note=note[:300], evidence=evidence,
                                     result=result, confidence=conf, source=source, version=(last.version + 1) if last else 1, created_by=user)
