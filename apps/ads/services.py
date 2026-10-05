"""Reklama tavsiyalari va shaffof sotuv prognozi (CONTRACTS §11.2-11.3). Raqamlarni KOD hisoblaydi, AI faqat izoh/matn yozadi."""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.core.settings_store import get_setting

from .models import AdCampaign, AdRecommendation, AdResult

DISCLAIMER = "Taxminiy prognoz: real natija farq qilishi mumkin. Kampaniya natijalari kiritilgach model sizning biznesingizga moslashadi."


@dataclass
class Coef:
    value: float
    source: str  # own_history | industry_template | manual | calibrated
    sample: int = 0


def z(values: list[float], x: float) -> float:
    if len(values) < 2:
        return 0.0
    sd = statistics.pstdev(values) or 1.0
    return (x - statistics.mean(values)) / sd


def find_candidates(business, limit: int = 10) -> list[AdRecommendation]:
    from apps.metrics.analytics import best_times, latest_metrics_qs
    min_age = float(get_setting("ads.min_age_hours", 24))
    w = get_setting("ads.score_weights", {"er": 0.4, "engagement": 0.3, "watch": 0.2, "recency": 0.1})
    rows = list(latest_metrics_qs(business.pk, since=timezone.now() - timedelta(days=45)))
    rows = [r for r in rows if (timezone.now() - r.post.published_at).total_seconds() / 3600 >= min_age]
    if not rows:
        return []
    ers = [r.er or 0 for r in rows]
    eng = [((r.saves or 0) + (r.shares or 0)) / max(1, r.reach or r.views or 1) for r in rows]
    wt = [(r.watch_time_sec or 0) / max(1, r.views or 1) for r in rows]
    bt = best_times(business)
    best_wd = bt["weekday"][0][0] if bt["weekday"] else None
    best_hr = bt["hour"][0][0] if bt["hour"] else None
    days = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
    out = []
    for r, e, g, t in zip(rows, ers, eng, wt):
        age_d = (timezone.now() - r.post.published_at).days
        recency = max(0.0, 1 - age_d / 45)
        score = w["er"] * z(ers, e) + w["engagement"] * z(eng, g) + w["watch"] * z(wt, t) + w["recency"] * recency
        reasons = [f"ER {e:.1%}" if e else "ER yo'q", f"saqlash+ulashish ulushi {g:.1%}"]
        if t:
            reasons.append(f"o'rtacha ko'rish vaqti {t:.1f}s")
        out.append((score, r, reasons))
    out.sort(key=lambda x: -x[0])
    top = out[:limit]
    tot = sum(max(0.01, s + 3) for s, _, _ in top) or 1
    AdRecommendation.objects.filter(business=business, status="new").delete()
    recs = []
    for s, r, reasons in top:
        when = f"{days[best_wd]} {best_hr:02d}:00 atrofida" if best_wd is not None and best_hr is not None else "Tarix yetarli emas"
        recs.append(AdRecommendation.objects.create(business=business, post=r.post, score=round(s, 3), reasons=reasons,
                                                    best_time=f"Post chiqqanidan 24–72 soat ichida; eng yaxshi: {when}",
                                                    budget_share=round(max(0.01, s + 3) / tot, 3)))
    return recs


def _tpl_defaults(business) -> dict:
    return (business.template.config.get("defaults") if business.template else None) or {"ctr": 0.012, "click_to_lead": 0.06, "cpm": 22000}


def coefficients(business, platform: str) -> dict[str, Coef]:
    """Har bir koeffitsiyent uchun qiymat + manba. Tarix bo'lsa — o'zniki (kalibrovka), aks holda andoza."""
    tpl = _tpl_defaults(business)
    rs = list(AdResult.objects.filter(campaign__business=business, campaign__platform=platform, spend__gt=0, impressions__gt=0))
    co = {"cpm": Coef(tpl["cpm"], "industry_template"), "ctr": Coef(tpl["ctr"], "industry_template"),
          "click_to_lead": Coef(tpl["click_to_lead"], "industry_template"),
          "lead_to_sale": Coef(business.lead_to_sale or 0.2, "manual"),
          "avg_check": Coef(float(business.avg_check or 0), "manual")}
    if len(rs) >= 3:
        alpha = 0.5
        def smooth(vals, base):
            v = base
            for x in vals:
                v = alpha * x + (1 - alpha) * v
            return v
        cpm = [float(r.spend) / r.impressions * 1000 for r in rs]
        ctr = [r.clicks / r.impressions for r in rs]
        co["cpm"] = Coef(smooth(cpm, tpl["cpm"]), "calibrated", len(rs))
        co["ctr"] = Coef(smooth(ctr, tpl["ctr"]), "calibrated", len(rs))
        cl = [(r.leads / r.clicks) for r in rs if r.clicks]
        if cl:
            co["click_to_lead"] = Coef(smooth(cl, tpl["click_to_lead"]), "calibrated", len(cl))
        ls = [(r.sales / r.leads) for r in rs if r.leads]
        if ls:
            co["lead_to_sale"] = Coef(smooth(ls, co["lead_to_sale"].value), "calibrated", len(ls))
        rev = [float(r.revenue) / r.sales for r in rs if r.sales]
        if rev:
            co["avg_check"] = Coef(smooth(rev, co["avg_check"].value or rev[0]), "calibrated", len(rev))
    return co


def forecast(business, budget: float, platform: str = "telegram_ads", margin: float | None = None) -> dict:
    """budget -> ko'rsatuv -> klik -> lead -> sotuv -> tushum -> ROI; 3 stsenariy (past/o'rtacha/yuqori)."""
    co = coefficients(business, platform)
    m = margin if margin is not None else (business.margin or 1.0)
    spread = {"past": dict(cpm=1.3, ctr=0.7, cl=0.7, ls=0.7), "ortacha": dict(cpm=1, ctr=1, cl=1, ls=1),
              "yuqori": dict(cpm=0.8, ctr=1.3, cl=1.3, ls=1.25)}
    scen = {}
    for name, f in spread.items():
        imp = budget / (co["cpm"].value * f["cpm"]) * 1000
        clicks = imp * min(1.0, co["ctr"].value * f["ctr"])
        leads = clicks * min(1.0, co["click_to_lead"].value * f["cl"])
        sales = leads * min(1.0, co["lead_to_sale"].value * f["ls"])
        revenue = sales * co["avg_check"].value
        roi = ((revenue * m - budget) / budget) if budget else None
        scen[name] = {"impressions": round(imp), "clicks": round(clicks), "leads": round(leads, 1), "sales": round(sales, 1),
                      "revenue": round(revenue), "roi": round(roi, 2) if roi is not None else None,
                      "cost_per_lead": round(budget / leads) if leads else None}
    return {"budget": budget, "platform": platform, "scenarios": scen, "disclaimer": DISCLAIMER,
            "assumptions": {k: {"value": round(c.value, 5), "source": c.source, "sample": c.sample} for k, c in co.items()},
            "warnings": (["O'rtacha chek kiritilmagan: tushum 0 ko'rinadi."] if not co["avg_check"].value else [])}


def record_result(campaign: AdCampaign, date, **kw) -> AdResult:
    r, _ = AdResult.objects.update_or_create(campaign=campaign, date=date, defaults=kw)
    return r


def campaign_variance(campaign: AdCampaign) -> dict:
    agg = campaign.results.aggregate(spend=Sum("spend"), imp=Sum("impressions"), clicks=Sum("clicks"), leads=Sum("leads"),
                                     sales=Sum("sales"), revenue=Sum("revenue"))
    fc = (campaign.forecast or {}).get("scenarios", {}).get("ortacha", {})
    def d(actual, plan):
        return None if not plan else round((actual - plan) / plan * 100, 1)
    return {"actual": {k: float(v or 0) for k, v in agg.items()}, "plan": fc,
            "diff_pct": {"clicks": d(float(agg["clicks"] or 0), fc.get("clicks")), "leads": d(float(agg["leads"] or 0), fc.get("leads")),
                         "sales": d(float(agg["sales"] or 0), fc.get("sales")), "revenue": d(float(agg["revenue"] or 0), fc.get("revenue"))}}


def telegram_ads_text(business, post_text: str, user=None, router=None) -> dict:
    """Telegram Ads matni (≤160 belgi) + auditoriya + taklif. Kampaniyani targetolog kabinetda o'zi yaratadi."""
    from apps.ai_router.router import generate
    from apps.ai_router.types import TaskType
    prompt = ('Telegram Ads uchun reklama matni yoz: matn 160 belgidan oshmasin, spamsiz, aniq foyda va chaqiriq bilan. '
              'JSON: {"variants":[{"text":"","button":""}],"channels_topics":["mavzu"],"audience":"","cpm_bid_hint":"","budget_hint":""}\n'
              f"Post: {post_text[:800]}")
    res, _ = generate(TaskType.AD_PLAN, prompt, business=business, kind="tg_ads", user=user, schema={"json": True}, router=router)
    d = res.data or {}
    for v in d.get("variants", []):
        if isinstance(v, dict) and len(v.get("text", "")) > 160:
            v["text"] = v["text"][:157].rstrip() + "..."
    return d


def campaign_blueprint(business, platform: str, objective: str, budget: float, post_text: str = "", user=None, router=None) -> dict:
    from apps.ai_router.router import generate
    from apps.ai_router.types import TaskType
    fc = forecast(business, budget, platform)
    prompt = ('Reklama kampaniyasi LOYIHASINI yoz. JSON: {"audience":{"age":"","regions":[],"interests":[]},"placements":[],"copy_variants":[""],'
              '"creative_advice":"","daily_budget":0,"stop_rule":"lead narxi X dan oshsa to\'xtat","test_phase":"","scale_phase":""}\n'
              f"Maqsad: {objective}; byudjet: {budget}; platforma: {platform}\nPost: {post_text[:600]}\n"
              f"Prognoz (o'zgartirma): {fc['scenarios']['ortacha']}")
    res, _ = generate(TaskType.AD_PLAN, prompt, business=business, kind="ad_plan", user=user, schema={"json": True}, router=router)
    return {"plan": res.data or {}, "forecast": fc}


def ads_advice(business, user=None, router=None) -> dict:
    """Ulanishsiz maslahat: qaysi postga, qaysi platformada (Meta Ads / Telegram Ads) reklama berish."""
    from apps.ai_router.router import generate
    from apps.ai_router.types import TaskType
    from apps.metrics.analytics import best_times, by_type, top_posts
    tops = [{"matn": r.post.text[:140], "platforma": r.post.account.platform if getattr(r.post, "account", None) else "", "tur": r.post.media_type, "er": r.er}
            for r in top_posts(business, 6)]
    cands = [{"matn": (c.post.text or "")[:120], "ball": round(c.score, 2), "sabab": c.reasons} for c in find_candidates(business, 5)]
    ctx = {"yaxshi_postlar": tops, "nomzodlar": cands, "turlar": by_type(business), "vaqtlar": best_times(business),
           "maqsad": business.main_goal, "oylik_reklama_byudjeti": float(business.monthly_ad_budget or 0), "o_rtacha_chek": float(business.avg_check or 0)}
    prompt = ("Sen performance-marketologsan. Biznes uchun reklama bo'yicha MASLAHAT ber (kabinetga ulanish yo'q, reklamani targetolog o'zi sozlaydi). "
              "Faqat Meta Ads (Instagram) va Telegram Ads ni ko'rib chiq. Byudjet 0 bo'lsa ham foizlarda taqsimla. Raqamlarni o'ylab topma. "
              'JSON: {"summary":"2-3 gap","platforms":[{"name":"meta_ads|telegram_ads","share_percent":0,"why":"","audience":"","format":""}],'
              '"promote_posts":[{"text":"post boshlanishi","where":"meta_ads|telegram_ads","why":""}],"new_creatives":["yangi reklama g\'oyasi"],'
              '"start_budget_hint":"","test_plan":"","avoid":["qilmaslik kerak"]}\n'
              f"Ma'lumot: {json.dumps(ctx, ensure_ascii=False, default=str)[:4500]}")
    res, gen = generate(TaskType.AD_PLAN, prompt, business=business, kind="ads_advice", user=user, schema={"json": True}, router=router)
    if not res.data:
        gen.data = {"summary": res.text or "Maslahat olinmadi."}
        gen.save(update_fields=["data"])
    return gen
