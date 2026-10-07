"""AI studiya, media tahlil, reklama, hisobotlar, havolalar."""
from __future__ import annotations

import hashlib
import json
from datetime import date

from django.utils.html import escape

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.ads import services as ads
from apps.ads.models import AdCampaign, AdRecommendation
from apps.connections.base import PlatformError
from apps.core import settings_store as ss
from apps.core.audit import audit
from apps.jobs.queue import enqueue
from apps.links import services as lsvc
from apps.links.models import ShortLink, WorkerStatus
from apps.media_analysis.models import MediaFile
from apps.reports.generator import default_period
from apps.reports.models import Report, ReportSchedule
from apps.studio import services as st
from . import spa, ui
from .common import get_obj


def mkform(fields: dict, data=None):
    return type("F", (forms.Form,), fields)(data)


def _ai_call(request, fn, *a, ok="Tayyor.", **kw):
    try:
        res = fn(*a, **kw)
        messages.success(request, ok)
        return res
    except Exception as e:  # noqa: BLE001
        messages.error(request, getattr(e, "user_message_uz", None) or f"AI xatosi: {e}")
        return None


# ---------------- AI studiya ----------------
WEEKDAYS = [("0", "Dushanba"), ("1", "Seshanba"), ("2", "Chorshanba"), ("3", "Payshanba"), ("4", "Juma"), ("5", "Shanba"), ("6", "Yakshanba")]
STUDIO_TABS = [("umumiy", "Umumiy"), ("reja", "Rejalar"), ("ssenariy", "Ssenariylar"), ("tahlil", "Tahlillar"), ("mavzu", "Dizayner mavzulari"), ("hook", "Hooklar")]


def _tabs_html(cur):
    return ui.tabs([(lbl, f"?tab={k}", k == cur) for k, lbl in STUDIO_TABS])


def _score_badge(v, mx=100):
    if v is None:
        return "—"
    r = v / mx
    return ui.badge(f"{v}/{mx}", "ok" if r >= .7 else "warn" if r >= .45 else "failed")


@login_required
@require_permission("ai_studio.view")
def studio_home(request):
    b = request.business
    if not b:
        messages.info(request, "AI studiya uchun biznesni tanlang.")
        return redirect("dashboard")
    from apps.ai_router.models import AIGeneration
    from apps.studio.models import ContentPlan, Hook, Script, ScriptAnalysis
    tab = request.GET.get("tab", "umumiy")
    tab = tab if tab in dict(STUDIO_TABS) else "umumiy"
    plat = forms.ChoiceField(label="Platforma", choices=[("telegram", "Telegram"), ("instagram", "Instagram"), ("youtube", "YouTube")])
    blocks = [_tabs_html(tab)]
    plans = ContentPlan.objects.filter(business=b).order_by("-created_at")
    scripts = Script.objects.filter(business=b).order_by("-created_at")
    if tab == "umumiy":
        cards = [("reja", "📅 Oylik reja", "AI butun oy uchun post mavzulari, hook va CTA tuzadi.", f"{plans.count()} ta reja"),
                 ("ssenariy", "🎬 Ssenariy", "Reels/Shorts/video uchun rejissyor ssenariysi: sahna, vaqt, matn.", f"{scripts.count()} ta ssenariy"),
                 ("tahlil", "🔍 Tahlil", "Ssenariy va tayyor videoni baholash: kuchli/kuchsiz joylar, nima tuzatish.", "ssenariy + video"),
                 ("mavzu", "🎨 Dizayner mavzulari", "Dizayner uchun aniq vazifalar: mavzu, vizual g'oya, ssenariy.", "rasm va video"),
                 ("hook", "🪝 Hook bazasi", "G'olib postlardan boshlanish jumlalari to'plami.", f"{Hook.objects.filter(business=b).count()} ta")]
        html = '<div class="grid g3">' + "".join(f'<a class="card" style="color:inherit;text-decoration:none" href="?tab={k}"><h2 style="margin:0 0 6px">{t}</h2><div class="muted" style="font-size:13px">{d}</div><div style="margin-top:8px"><b>{n}</b> →</div></a>' for k, t, d, n in cards) + "</div>"
        blocks.append({"type": "html", "html": html})
        blocks.append(ui.form_block(mkform({"topic": forms.CharField(label="Mavzu"), "platform": plat}), "Tezkor caption va hashtaglar", "Yaratish", action="/studiya/caption/"))
    elif tab == "reja":
        month = forms.CharField(label="Oy (YYYY-MM)", initial=date.today().strftime("%Y-%m"))
        blocks.append(ui.form_block(mkform({"platform": plat, "month": month}), "Oylik kontent-reja", "AI bilan reja tuzish", action="/studiya/reja/",
                                    intro="AI sizning statistikangiz asosida oy uchun post kalendarini tuzadi. Keyin uni bir tugma bilan kalendarga qoralama qilib yuklaysiz."))
        blocks.append(ui.table("Rejalar", ["Oy", "Platforma", "Yozuvlar", "Kalendarga", ""],
                               [[f"{p.month:%Y-%m}", p.platform, len(p.entries), "Yuklangan" if p.loaded_to_calendar else "Yo'q", ui.link("Ochish", f"/studiya/reja/{p.pk}/")] for p in plans[:20]], "Hali reja tuzilmagan."))
    elif tab == "ssenariy":
        blocks.append(ui.form_block(mkform({"brief": forms.CharField(label="Qisqa maqsad", widget=forms.Textarea(attrs={"rows": 2})), "fmt": forms.ChoiceField(label="Format", choices=Script.FORMATS)}),
                                    "Ssenariy yozish", "Ssenariy yozish", action="/studiya/ssenariy/", intro="Rejissyor uslubida: hook, sahnalar vaqt bilan, matn, CTA."))
        sc = {a.script_id: a.score for a in ScriptAnalysis.objects.filter(script__in=[s.pk for s in scripts[:20]]).order_by("created_at")}
        blocks.append(ui.table("Ssenariylar", ["Sarlavha", "Format", "Baho", "Sana", ""],
                               [[s.title, s.get_fmt_display(), _score_badge(sc.get(s.pk)), ui.dt(s.created_at), ui.link("Ochish", f"/studiya/ssenariy/{s.pk}/")] for s in scripts[:20]], "Hali ssenariy yo'q."))
    elif tab == "tahlil":
        mrows = []
        from apps.media_analysis.models import MediaFile
        for m in MediaFile.objects.filter(business=b).order_by("-created_at")[:15]:
            an = m.analyses.first()
            sc = (an.ai or {}).get("score") if an and an.ai else None
            mrows.append([ui.link(m.original_name, f"/media/{m.pk}/"), m.get_kind_display() if hasattr(m, "get_kind_display") else m.kind, _score_badge(sc), ui.badge(m.status, m.status), ui.dt(m.created_at)])
        blocks.append({"type": "html", "html": '<div class="row sb"><div><b>Video va rasm tahlili</b><div class="muted" style="font-size:13px">Tayyor faylni yuklang — AI uni sahna-sahna ko\'radi va bir qarashda tushunarli kartada ko\'rsatadi.</div></div><a class="btn primary" href="/media/">⬆ Yangi tahlil</a></div>'})
        blocks.append(ui.table(None, ["Fayl", "Tur", "Baho", "Holat", "Sana"], mrows, "Hali media tahlil qilinmagan."))
        srows = [[ui.link(a.script.title, f"/studiya/ssenariy/{a.script_id}/"), _score_badge(a.score), ui.dt(a.created_at)] for a in ScriptAnalysis.objects.filter(script__business=b).select_related("script").order_by("-created_at")[:15]]
        blocks.append(ui.table("Ssenariy tahlillari", ["Ssenariy", "Baho", "Sana"], srows, "Ssenariy sahifasida «Ssenariyni tahlil qilish» tugmasini bosing."))
    elif tab == "mavzu":
        tg = AIGeneration.objects.filter(business=b, kind="design_topics").exclude(data=None).order_by("-created_at")[:10]
        blocks.append(ui.form_block(mkform({"platform": forms.ChoiceField(label="Platforma", required=False, choices=[("", "Hammasi"), ("telegram", "Telegram"), ("instagram", "Instagram"), ("youtube", "YouTube")])}),
                                    "Dizayner uchun mavzular (rasm/video)", "AI mavzu taklif qilsin", intro="AI tahlil asosida dizayner nima tayyorlashi kerakligini yozadi: mavzu, vizual vazifa, ssenariy.", action="/studiya/mavzular/"))
        blocks.append(ui.table("Oxirgi mavzular to'plami", ["Sana", ""], [[ui.dt(g.created_at), ui.link("Ochish", f"/studiya/mavzular/{g.pk}/")] for g in tg], "Hali yo'q."))
    else:
        hooks = Hook.objects.filter(business=b).order_by("-created_at")[:30]
        blocks.append({"type": "actions", "title": "Hook bazasi", "buttons": [ui.btn("G'olib postlardan hooklar olish", "/studiya/hook-yangila/")]})
        blocks.append(ui.table("Hooklar", ["Hook", "Manba", "Holat"], [[h.text[:140], h.source, h.status] for h in hooks], "Hali hook yo'q."))
    return ui.page(request, "AI studiya", blocks, subtitle=b.name)


@login_required
@require_POST
@require_permission("ai_studio.create")
def studio_plan(request):
    b = request.business
    try:
        y, m = (int(x) for x in request.POST["month"].split("-"))
    except (KeyError, ValueError):
        messages.error(request, "Oy formati: YYYY-MM")
        return redirect("/studiya/?tab=reja")
    p = _ai_call(request, st.monthly_plan, b, request.POST.get("platform", "telegram"), date(y, m, 1), request.user, ok="Reja tayyor. Ko'rib chiqib kalendarga yuklang.")
    return redirect(f"/studiya/reja/{p.pk}/" if p else "/studiya/?tab=reja")


@login_required
def studio_plan_view(request, pk):
    from apps.studio.models import ContentPlan
    p = get_obj(request, ContentPlan, pk, "ai_studio.view")
    rows = [[e.get("date"), e.get("format"), e.get("topic"), e.get("hook"), e.get("cta")] for e in p.entries]
    acts = [] if p.loaded_to_calendar else [ui.btn("Kalendarga yuklash (qoralama)", f"/studiya/reja/{p.pk}/yuklash/", "primary")]
    return ui.page(request, f"Reja {p.month:%Y-%m} · {p.platform}", [{"type": "text", "title": "Strategiya", "text": p.summary}, ui.table("Reja", ["Sana", "Format", "Mavzu", "Hook", "CTA"], rows),
                                                                    {"type": "actions", "title": "Amallar", "buttons": acts}], toolbar=[{"label": "Orqaga", "url": "/studiya/"}])


@login_required
@require_POST
def studio_plan_load(request, pk):
    from apps.studio.models import ContentPlan
    p = get_obj(request, ContentPlan, pk, "calendar.create")
    n = st.load_plan_to_calendar(p, request.user)
    messages.success(request, f"{n} ta qoralama kalendarga yuklandi (AI qoralamasi: inson ko'rib chiqishi shart).")
    return redirect("calendar")


@login_required
@require_POST
@require_permission("scripts.create")
def studio_script(request):
    s = _ai_call(request, st.generate_script, request.business, request.POST.get("brief", ""), request.POST.get("fmt", "reel"), 2, request.user)
    return redirect(f"/studiya/ssenariy/{s.pk}/" if s else "/studiya/?tab=ssenariy")


@login_required
def studio_script_view(request, pk):
    from apps.studio.models import Script
    from apps.web.analysis_view import normalize_script
    s = get_obj(request, Script, pk, "scripts.view")
    d = s.body if isinstance(s.body, dict) else {}
    blocks = []
    an = s.analyses.order_by("-created_at").first() if hasattr(s, "analyses") else None
    card = normalize_script(an)
    if card:
        bars = "".join(f'<div class="an-bar"><span>{c["label"]}</span><div class="an-track"><i class="{c["cls"]}" style="width:{c["pct"]}%"></i></div><b>{c["v"]}</b></div>' for c in card["scores"])
        fixes = "".join(f"<li>{escape(x)}</li>" for x in card["fixes"])
        blocks.append({"type": "html", "title": f"Ssenariy bahosi: {card['total']}/100", "html": f'<div class="an-wrap">{bars}</div>' + (f"<h3>Nima tuzatish kerak</h3><ol>{fixes}</ol>" if fixes else "")})
    blocks.append({"type": "text", "title": s.title, "text": st.script_text(d) if d.get("scenes") else (json.dumps(d, ensure_ascii=False, indent=2) if d else s.raw_text)})
    blocks.append({"type": "actions", "title": "Amallar", "buttons": [ui.btn("Ssenariyni tahlil qilish", f"/studiya/ssenariy/{s.pk}/tahlil/", "primary")]})
    return ui.page(request, "Ssenariy", blocks, toolbar=[{"label": "Orqaga", "url": "/studiya/?tab=ssenariy"}])


@login_required
@require_POST
def studio_script_analyze(request, pk):
    from apps.studio.models import Script
    s = get_obj(request, Script, pk, "scripts.edit")
    _ai_call(request, st.analyze_script, s, request.user, ok="Tahlil tayyor.")
    return redirect("studio_script_view", pk=s.pk)


@login_required
@require_POST
@require_permission("ai_studio.create")
def studio_caption(request):
    d = _ai_call(request, st.captions, request.business, request.POST.get("topic", ""), request.POST.get("platform", "telegram"), request.user)
    if d is not None:
        return ui.page(request, "Caption variantlari", [{"type": "text", "title": None, "text": json.dumps(d, ensure_ascii=False, indent=2)}], toolbar=[{"label": "Orqaga", "url": "/studiya/"}])
    return redirect("studio_home")


@login_required
@require_POST
@require_permission("hooks.edit")
def studio_hooks_refresh(request):
    n = st.refresh_hook_suggestions(request.business)
    messages.success(request, f"{n} ta hook qo'shildi.")
    return redirect("/studiya/?tab=hook")


# ---------------- Media tahlil ----------------
@login_required
@require_permission("media_analysis.view")
def media_list(request):
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "media_analysis.view").values_list("pk", flat=True))
    qs = MediaFile.objects.filter(business_id__in=ids).order_by("-created_at")[:40]
    rows = [[ui.link(m.original_name, f"/media/{m.pk}/"), m.business.name, ui.badge(m.status, m.status), ui.dt(m.created_at)] for m in qs.select_related("business")]
    blocks = [ui.table(None, ["Fayl", "Biznes", "Holat", "Sana"], rows, "Hali media yuklanmagan.")]
    if request.business and perms.can(request.user, "media_analysis.create", request.business):
        blocks.append(ui.form_block(mkform({"file": forms.FileField(label="Video yoki rasm")}), "Yangi tahlil", "Yuklash va tahlil qilish", action="/media/yuklash/"))
    return ui.page(request, "Media tahlil", blocks)


@login_required
@require_POST
@require_permission("media_analysis.create")
def media_upload(request):
    f, b = request.FILES.get("file"), request.business
    if not f or not b:
        messages.error(request, "Biznesni tanlang va fayl yuklang.")
        return redirect("media_list")
    ext = f.name.rsplit(".", 1)[-1].lower()
    if ext not in ("mp4", "mov", "jpg", "jpeg", "png", "webp"):
        messages.error(request, "Ruxsat etilgan: mp4, mov, jpg, png, webp")
        return redirect("media_list")
    h = hashlib.sha256()
    for ch in f.chunks():
        h.update(ch)
    f.seek(0)
    m = MediaFile.objects.create(business=b, file=f, original_name=f.name[:200], kind="video" if ext in ("mp4", "mov") else "image", sha256=h.hexdigest(), size=f.size, uploaded_by=request.user)
    j = enqueue("media_analyze", {"media_file_id": m.pk}, queue="media", business_id=b.pk)
    if j:
        m.job_id = j.pk
        m.save(update_fields=["job_id"])
    messages.success(request, "Yuklandi, tahlil navbatda (katta videolar bir necha daqiqa oladi).")
    return redirect("media_detail", pk=m.pk)


@login_required
def media_detail(request, pk):
    from apps.web.analysis_view import normalize_media
    m = get_obj(request, MediaFile, pk, "media_analysis.view")
    a = m.analyses.order_by("-created_at").first()
    tech = [(k, v) for k, v in ((a.technical if a else {}) or {}).items() if not isinstance(v, (list, dict))]
    tr = a.transcript if a else None
    return spa.respond(request, {
        "kind": "media_detail", "id": m.pk, "name": m.original_name, "business": m.business.name, "size": m.size, "at": ui.dt(m.created_at), "status": m.status,
        "card": normalize_media(a.ai) if a else None, "tech": [[k, str(v)] for k, v in tech], "degraded": bool(a and a.degraded), "has_analysis": bool(a),
        "transcript": (tr if isinstance(tr, str) else (tr or {}).get("text", "")) if tr else "", "raw": json.dumps(a.ai, ensure_ascii=False, indent=2) if a and a.ai else "",
        "running": m.status in ("pending", "running")})


# ---------------- Reklama ----------------
@login_required
@require_permission("ads.view")
def ads_home(request):
    b = request.business
    if not b:
        messages.info(request, "Reklama uchun biznesni tanlang.")
        return redirect("dashboard")
    recs = AdRecommendation.objects.filter(business=b, status="new").select_related("post").order_by("-score")[:10]
    camps = AdCampaign.objects.filter(business=b).order_by("-created_at")[:15]
    fq = mkform({"budget": forms.FloatField(label="Byudjet", min_value=0), "platform": forms.ChoiceField(label="Platforma", choices=AdCampaign.PLATFORMS)})
    blocks = [ui.table("Reklamaga arziydigan postlar", ["Post", "Ball", "Sabab", "Eng yaxshi vaqt", ""],
                       [[(r.post.text or "")[:70], round(r.score, 2), "; ".join(map(str, r.reasons))[:120], r.best_time, ui.btn("Kampaniya loyihasi", f"/reklama/tavsiya/{r.pk}/", "primary")] for r in recs],
                       "Hozircha tavsiya yo'q (postlar yetarlicha yoshga yetmagan yoki ma'lumot kam)."),
              ui.table("Kampaniyalar", ["Nomi", "Platforma", "Byudjet", "Holat", ""], [[c.name, c.get_platform_display(), c.budget, ui.badge(c.get_status_display(), c.status), ui.link("Ochish", f"/reklama/{c.pk}/")] for c in camps]),
              ui.form_block(fq, "Prognoz kalkulyatori", "Hisoblash", action="/reklama/prognoz/")]
    blocks.append({"type": "actions", "title": "Tavsiyalar", "buttons": [ui.btn("Tavsiyalarni yangilash", "/reklama/yangila/")]})
    return ui.page(request, "Reklama", blocks, subtitle=b.name, toolbar=[{"label": "AI maslahat: qayerga reklama berish?", "url": "/reklama/maslahat/", "cls": "primary"}])


@login_required
@require_POST
@require_permission("ads.edit")
def ads_refresh(request):
    n = len(ads.find_candidates(request.business))
    messages.success(request, f"{n} ta nomzod topildi.")
    return redirect("ads_home")


@login_required
@require_POST
@require_permission("ads.view")
def ads_forecast(request):
    try:
        fc = ads.forecast(request.business, float(request.POST.get("budget", 0)), request.POST.get("platform", "telegram_ads"))
    except ValueError:
        messages.error(request, "Byudjetni raqam bilan kiriting.")
        return redirect("ads_home")
    rows = [[k, v["impressions"], v["clicks"], v["leads"], v["sales"], v["revenue"], v["roi"], v["cost_per_lead"]] for k, v in fc["scenarios"].items()]
    return ui.page(request, "Prognoz", [ui.table("3 stsenariy", ["Stsenariy", "Ko'rsatuv", "Klik", "Murojaat", "Sotuv", "Tushum", "ROI", "Murojaat narxi"], rows),
                                      ui.table("Taxminlar manbasi", ["Ko'rsatkich", "Qiymat", "Manba", "Namuna"], [[k, v["value"], v["source"], v["sample"]] for k, v in fc["assumptions"].items()]),
                                      {"type": "text", "title": "Ogohlantirish", "text": fc["disclaimer"] + ("\n" + "\n".join(fc["warnings"]) if fc["warnings"] else "")}],
                   toolbar=[{"label": "Orqaga", "url": "/reklama/"}])


@login_required
@require_POST
def ads_recommendation(request, pk):
    r = get_obj(request, AdRecommendation, pk, "ads.create")
    bp = _ai_call(request, ads.campaign_blueprint, r.business, "telegram_ads", "lead", float(r.business.monthly_ad_budget or 0), r.post.text or "", request.user, ok="Loyiha tayyor.")
    if bp:
        c = AdCampaign.objects.create(business=r.business, name=f"Kampaniya: {(r.post.text or '')[:40]}", platform="telegram_ads", objective="lead", budget=r.business.monthly_ad_budget or 0,
                                      post=r.post, plan=bp["plan"], forecast=bp["forecast"], created_by=request.user)
        r.status = "accepted"
        r.save(update_fields=["status"])
        return redirect("ads_campaign", pk=c.pk)
    return redirect("ads_home")


@login_required
def ads_campaign(request, pk):
    c = get_obj(request, AdCampaign, pk, "ads.view")
    res = c.results.order_by("-date")[:30]
    blocks = [{"type": "text", "title": "Kampaniya loyihasi (targetolog kabinetda o'zi yaratadi)", "text": json.dumps(c.plan, ensure_ascii=False, indent=2)},
              ui.table("Natijalar", ["Sana", "Sarf", "Ko'rsatuv", "Klik", "Murojaat", "Sotuv", "Tushum"], [[r.date, r.spend, r.impressions, r.clicks, r.leads, r.sales, r.revenue] for r in res]),
              ui.kv("Reja va fakt farqi", [(k, v) for k, v in ads.campaign_variance(c).get("diff_pct", {}).items()] if c.results.exists() else [("—", "Natija kiritilmagan")])]
    blocks.append(ui.form_block(mkform({"date": forms.DateField(label="Sana", initial=date.today, widget=forms.DateInput(attrs={"type": "date"})), "spend": forms.FloatField(label="Sarf", initial=0),
                                        "impressions": forms.IntegerField(label="Ko'rsatuv", initial=0), "clicks": forms.IntegerField(label="Klik", initial=0), "leads": forms.IntegerField(label="Murojaat", initial=0),
                                        "sales": forms.IntegerField(label="Sotuv", initial=0), "revenue": forms.FloatField(label="Tushum", initial=0)}),
                                "Natija kiritish (qo'lda)", "Saqlash", action=f"/reklama/{c.pk}/natija/"))
    return ui.page(request, c.name, blocks, subtitle=c.business.name, toolbar=[{"label": "Orqaga", "url": "/reklama/"}])


@login_required
@require_POST
def ads_result(request, pk):
    c = get_obj(request, AdCampaign, pk, "ads.edit")
    try:
        ads.record_result(c, date.fromisoformat(request.POST["date"]), spend=float(request.POST.get("spend") or 0), impressions=int(request.POST.get("impressions") or 0),
                          clicks=int(request.POST.get("clicks") or 0), leads=int(request.POST.get("leads") or 0), sales=int(request.POST.get("sales") or 0), revenue=float(request.POST.get("revenue") or 0))
        messages.success(request, "Natija saqlandi. Prognoz modeli moslashadi.")
    except (ValueError, KeyError):
        messages.error(request, "Qiymatlarni tekshiring.")
    return redirect("ads_campaign", pk=c.pk)


# ---------------- Hisobotlar ----------------
@login_required
@require_permission("reports.view")
def report_list(request):
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "reports.view").values_list("pk", flat=True))
    rows = []
    for r in Report.objects.filter(business_id__in=ids).select_related("business").order_by("-created_at")[:40]:
        rows.append([ui.link(f"{r.get_kind_display()} · {r.period_start:%d.%m}–{r.period_end:%d.%m}", f"/hisobotlar/{r.pk}/"), r.business.name, ui.badge(r.get_status_display() if hasattr(r, "get_status_display") else r.status, r.status), ui.dt(r.created_at)])
    blocks = [ui.table(None, ["Hisobot", "Biznes", "Holat", "Yaratilgan"], rows, "Hisobot yo'q.")]
    if request.business and perms.can(request.user, "reports.create", request.business):
        blocks.append(ui.form_block(mkform({"kind": forms.ChoiceField(label="Tur", choices=Report.KINDS)}), "Yangi hisobot", "Yaratish", action="/hisobotlar/yaratish/"))
        sch = ReportSchedule.objects.filter(business=request.business)
        blocks.append(ui.table("Avtomatik jadval", ["Tur", "Kun", "Soat", "Avto-yuborish", "Holat"],
                               [[s.get_kind_display(), dict(WEEKDAYS).get(str(s.weekday), s.weekday) if s.kind == "weekly" else f"{s.day_of_month}-sana", f"{s.hour}:00", "Ha" if s.auto_send else "Yo'q", "Faol" if s.active else "O'chiq"] for s in sch]))
        blocks.append(ui.form_block(mkform({"kind": forms.ChoiceField(label="Tur", choices=Report.KINDS[:2]), "weekday": forms.ChoiceField(label="Haftalik hisobot qaysi kuni yuborilsin", choices=WEEKDAYS, initial="0"),
                                            "day_of_month": forms.IntegerField(label="Oy kuni", initial=1, min_value=1, max_value=28), "hour": forms.IntegerField(label="Soat (Toshkent vaqti)", initial=9, min_value=0, max_value=23),
                                            "auto_send": forms.BooleanField(label="Mijozga avtomatik yuborish", required=False)}),
                                    "Mijozga avtomatik hisobot jadvali", "Saqlash", action="/hisobotlar/jadval/",
                                    intro="Masalan: Tur = Haftalik, Kun = Dushanba, Soat = 9, «avtomatik yuborish» belgilangan — har dushanba ertalab mijozga Telegram bot orqali qisqa xulosa boradi. Kun va soatni o'zingiz tanlaysiz."))
    return ui.page(request, "Hisobotlar", blocks)


@login_required
@require_POST
@require_permission("reports.create")
def report_create(request):
    b, kind = request.business, request.POST.get("kind", "weekly")
    ps, pe = default_period(kind)
    r = Report.objects.create(business=b, kind=kind, period_start=ps, period_end=pe, created_by=request.user)
    enqueue("report_generate", {"report_id": r.pk}, queue="system", business_id=b.pk)
    messages.success(request, "Hisobot tayyorlanmoqda (bir necha soniya).")
    audit("report.create", user=request.user, business_id=b.pk, target=f"report:{r.pk}", detail={"kind": kind})
    return redirect("report_detail", pk=r.pk)


@login_required
@require_POST
@require_permission("reports.create")
def report_schedule(request):
    b = request.business
    kind = request.POST.get("kind", "weekly")
    ReportSchedule.objects.update_or_create(business=b, kind=kind, defaults={
        "weekday": int(request.POST.get("weekday") or 0), "day_of_month": int(request.POST.get("day_of_month") or 1), "hour": int(request.POST.get("hour") or 9),
        "auto_send": request.POST.get("auto_send") == "on", "requires_approval": False, "active": True})
    messages.success(request, "Jadval saqlandi.")
    return redirect("report_list")


@login_required
def report_detail(request, pk):
    r = get_obj(request, Report, pk, "reports.view")
    blocks = [ui.kv("Hisobot", [("Davr", f"{r.period_start} — {r.period_end}"), ("Holat", r.status), ("Xato", r.error or "—"), ("Mijozga yuborilgan", ui.dt(r.delivered_at))])]
    if r.summary_text:
        blocks.append({"type": "text", "title": "AI xulosa", "text": r.summary_text})
    acts = []
    if r.pdf:
        acts.append({"t": "PDF", "label": "PDF yuklab olish", "post": None})
    html = ""
    if r.data:
        html += f'<a class="btn primary" href="/hisobotlar/{r.pk}/korinish/">Chiroyli sahifada ko\'rish</a> '
    if r.pdf:
        html += f'<a class="btn" href="/hisobotlar/{r.pk}/fayl/pdf/">PDF yuklab olish</a> '
    if r.xlsx:
        html += f'<a class="btn" href="/hisobotlar/{r.pk}/fayl/xlsx/">Excel yuklab olish</a>'
    if html:
        blocks.append({"type": "html", "title": "Fayllar", "html": html})
    btns = []
    if r.status in ("ready", "awaiting_approval") and perms.can(request.user, "reports.export", r.business):
        btns.append(ui.btn("Mijozga Telegram orqali yuborish", f"/hisobotlar/{r.pk}/yuborish/", "primary", "Hisobot mijoz botiga yuborilsinmi?"))
    if btns:
        blocks.append({"type": "actions", "title": "Amallar", "buttons": btns})
    return ui.page(request, f"{r.get_kind_display()} hisobot", blocks, subtitle=r.business.name, toolbar=[{"label": "Orqaga", "url": "/hisobotlar/"}])


@login_required
def report_view(request, pk):
    from apps.reports import design
    r = get_obj(request, Report, pk, "reports.view")
    if not r.data:
        messages.info(request, "Hisobot hali tayyor emas.")
        return redirect("report_detail", pk=r.pk)
    ctx = design.html_context(r)
    ctx.update({"public": False, "can_share": perms.can(request.user, "reports.export", r.business), "share_url": request.session.pop("share_url", "")})
    return render(request, "report_view.html", ctx)


@login_required
@require_POST
def report_share(request, pk):
    import secrets
    from datetime import timedelta
    r = get_obj(request, Report, pk, "reports.export")
    r.share_token, r.share_expires = secrets.token_urlsafe(24), timezone.now() + timedelta(days=14)
    r.save(update_fields=["share_token", "share_expires"])
    base = (ss.get_setting("general.public_url", "") or request.build_absolute_uri("/")).rstrip("/")
    request.session["share_url"] = f"{base}/h/{r.share_token}/"
    audit("report.share", user=request.user, business_id=r.business_id, target=f"report:{r.pk}")
    return redirect("report_view", pk=r.pk)


def report_public(request, token):
    """Maxfiy havola orqali ko'rish (login yo'q; faqat hisobot raqamlari, 14 kun)."""
    from apps.reports import design
    r = Report.objects.filter(share_token=token, share_expires__gt=timezone.now()).first() if len(token) >= 20 else None
    if r is None or not r.data:
        raise Http404
    ctx = design.html_context(r)
    ctx.update({"public": True, "can_share": False, "share_url": ""})
    resp = render(request, "report_view.html", ctx)
    resp["Referrer-Policy"] = "no-referrer"
    resp["X-Robots-Tag"] = "noindex"
    return resp


@login_required
def report_file(request, pk, kind):
    r = get_obj(request, Report, pk, "reports.export")
    f = r.pdf if kind == "pdf" else r.xlsx if kind == "xlsx" else None
    if not f:
        raise Http404
    return FileResponse(f.open("rb"), as_attachment=True, filename=f"hisobot_{r.pk}.{kind}")


@login_required
@require_POST
def report_deliver(request, pk):
    r = get_obj(request, Report, pk, "reports.export")
    enqueue("report_deliver", {"report_id": r.pk}, queue="system", business_id=r.business_id)
    audit("report.deliver", user=request.user, business_id=r.business_id, target=f"report:{r.pk}")
    messages.success(request, "Yuborish navbatga qo'yildi.")
    return redirect("report_detail", pk=r.pk)


# ---------------- Havolalar ----------------
@login_required
@require_permission("links.view")
def link_list(request):
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "links.view").values_list("pk", flat=True))
    rows = []
    for l in ShortLink.objects.filter(business_id__in=ids).select_related("business").order_by("-created_at")[:60]:
        rows.append([lsvc.short_url(l), l.target_url[:60], l.business.name, l.clicks.count(), ui.badge("Sinxron" if l.synced else "Kutmoqda", "ok" if l.synced else "warn", l.sync_error[:80] or None),
                     ui.btn("O'chirish", f"/havolalar/{l.pk}/ochir/", "danger", "Havola o'chirilsinmi?")])
    ws = WorkerStatus.objects.first()
    blocks = [{"type": "html", "title": "Qisqa havola nima uchun kerak?", "html": (
        "<p><b>Muammo:</b> postga uzun havola qo'ysangiz (masalan, <code>sayt.uz/kurslar?utm_source=instagram&utm_campaign=oktabr</code>) u xunuk ko'rinadi va kim bosganini bilib bo'lmaydi.</p>"
        "<p><b>Yechim:</b> bu yerda uzun havolani qisqa havolaga aylantirasiz (<code>sizning-domen.uz/kurs1</code>). Mijoz uni bosganda o'z saytingizga o'tadi, tizim esa <b>nechta odam bosganini</b> sanaydi.</p>"
        "<ol><li>«Maqsad URL» — mijoz oxirida borishi kerak bo'lgan sahifa (sayt, Telegram bot, ro'yxatdan o'tish formasi).</li>"
        "<li>«Slug» — qisqa nom (masalan <code>kurs1</code>). Bo'sh qoldirsangiz tizim o'zi tuzadi.</li>"
        "<li>utm maydonlari — ixtiyoriy. Qaysi post/platformadan kelganini saytingiz statistikasida ko'rish uchun (masalan utm_source = instagram).</li>"
        "<li>«Yaratish»dan keyin qisqa havolani nusxalab, postingiz matniga qo'ying.</li></ol>"
        "<p class='muted'>Eslatma: bu funksiya Cloudflare Worker orqali ishlaydi (Sozlamalar → Kalitlar → Cloudflare Worker). Worker ulanmagan bo'lsa, havola «Kutmoqda» holatida turadi. Kerak bo'lmasa bu bo'limni ishlatmasangiz ham bo'ladi.</p>")},
              {"type": "html", "html": f"Worker: <b>{'ishlayapti' if ws and ws.ok else 'tekshirilmagan / xato'}</b> {ws.message if ws else ''} · bugungi klik: {ws.clicks_today if ws else 0}"},
              ui.table(None, ["Qisqa havola", "Maqsad", "Biznes", "Klik", "Holat", ""], rows, "Havola yo'q.")]
    if request.business and perms.can(request.user, "links.create", request.business):
        blocks.append(ui.form_block(mkform({"target_url": forms.URLField(label="Maqsad URL"), "slug": forms.SlugField(label="Slug (ixtiyoriy)", required=False),
                                            "utm_source": forms.CharField(label="utm_source", required=False), "utm_medium": forms.CharField(label="utm_medium", required=False),
                                            "utm_campaign": forms.CharField(label="utm_campaign", required=False), "note": forms.CharField(label="Izoh", required=False)}),
                                    "Yangi qisqa havola", "Yaratish", action="/havolalar/yaratish/"))
    blocks.append({"type": "actions", "title": "Worker", "buttons": [ui.btn("Kliklarni hozir yangilash", "/havolalar/sinxron/")]})
    return ui.page(request, "Havolalar", blocks)


@login_required
@require_POST
@require_permission("links.create")
def link_create(request):
    utm = {k: request.POST[k] for k in ("utm_source", "utm_medium", "utm_campaign") if request.POST.get(k)}
    try:
        l = lsvc.create_link(request.business, request.POST["target_url"], slug=request.POST.get("slug") or None, utm=utm, note=request.POST.get("note", ""))
        messages.success(request, f"Yaratildi: {lsvc.short_url(l)}")
        audit("link.create", user=request.user, business_id=request.business.pk, target=f"link:{l.pk}", detail={"url": request.POST["target_url"][:120]})
    except PlatformError as e:
        messages.error(request, e.user_message_uz or str(e))
    except Exception as e:  # noqa: BLE001
        messages.error(request, f"Xato: {e} (slug band bo'lishi mumkin)")
    return redirect("link_list")


@login_required
@require_POST
def link_delete(request, pk):
    l = get_obj(request, ShortLink, pk, "links.delete")
    lsvc.remove_link(l)
    audit("link.delete", user=request.user, business_id=l.business_id, target=f"link:{pk}")
    return redirect("link_list")


@login_required
@require_POST
@require_permission("links.view")
def link_sync(request):
    try:
        r = lsvc.sync_clicks()
        messages.success(request, f"{r['clicks']} ta yangi klik.")
    except PlatformError as e:
        messages.error(request, e.user_message_uz or str(e))
    return redirect("link_list")


def _latest_gen(business, kind):
    from apps.ai_router.models import AIGeneration
    return AIGeneration.objects.filter(business=business, kind=kind).exclude(data=None).order_by("-created_at").first()


def _bullets(title, items):
    items = [str(i) for i in (items or []) if i]
    return {"type": "text", "title": title, "text": "\n".join("• " + i for i in items)} if items else None


# ---------------- Dizayner uchun mavzular ----------------
@login_required
@require_POST
@require_permission("ai_studio.create")
def studio_topics(request):
    g = _ai_call(request, st.design_topics, request.business, request.POST.get("platform", ""), 8, request.user, ok="Mavzular tayyor.")
    return redirect(f"/studiya/mavzular/{g.pk}/" if g else "/studiya/?tab=mavzu")


@login_required
@require_permission("ai_studio.view")
def studio_topics_view(request, pk):
    from apps.ai_router.models import AIGeneration
    g = get_obj(request, AIGeneration, pk, "ai_studio.view", business_field="business")
    d = g.data or {}
    rows = [[t.get("platform"), t.get("format"), t.get("topic"), t.get("why"), t.get("visual_brief"), t.get("script"), t.get("best_time")] for t in d.get("topics", []) if isinstance(t, dict)]
    blocks = [{"type": "text", "title": "Nega aynan shu mavzular", "text": d.get("summary", "")},
              ui.table("Dizayner uchun topshiriqlar", ["Platforma", "Format", "Mavzu", "Sabab (tahlil)", "Vizual vazifa", "Ssenariy", "Vaqt"], rows, "Mavzu yo'q."),
              {"type": "actions", "title": "Amallar", "buttons": [ui.btn("Kalendarga qoralama qilib qo'shish", f"/studiya/mavzular/{g.pk}/yuklash/", "primary")]}]
    return ui.page(request, "Dizayner uchun mavzular", blocks, toolbar=[{"label": "Orqaga", "url": "/studiya/"}])


@login_required
@require_POST
def studio_topics_load(request, pk):
    from apps.ai_router.models import AIGeneration
    g = get_obj(request, AIGeneration, pk, "calendar.create", business_field="business")
    n = st.load_topics_to_calendar(g, request.user)
    messages.success(request, f"{n} ta topshiriq qoralama sifatida kalendarga qo'shildi. Dizayner rasm/video yuklab, vaqt qo'ysa avtomatik rejalashtiriladi.")
    return redirect("calendar")


# ---------------- Reklama maslahati ----------------
@login_required
@require_POST
@require_permission("ads.view")
def ads_advice_run(request):
    g = _ai_call(request, ads.ads_advice, request.business, request.user, ok="Maslahat tayyor.")
    return redirect("ads_advice_view") if g else redirect("ads_home")


@login_required
@require_permission("ads.view")
def ads_advice_view(request):
    b = request.business
    if not b:
        return redirect("dashboard")
    g = _latest_gen(b, "ads_advice")
    blocks = []
    if g:
        d = g.data or {}
        blocks.append({"type": "text", "title": f"Xulosa ({ui.dt(g.created_at)})", "text": d.get("summary", "")})
        blocks.append(ui.table("Qaysi platformaga", ["Platforma", "Ulush %", "Nega", "Auditoriya", "Format"],
                               [[x.get("name"), x.get("share_percent"), x.get("why"), x.get("audience"), x.get("format")] for x in d.get("platforms", []) if isinstance(x, dict)]))
        blocks.append(ui.table("Qaysi postlarni reklama qilish", ["Post", "Qayerda", "Nega"],
                               [[x.get("text"), x.get("where"), x.get("why")] for x in d.get("promote_posts", []) if isinstance(x, dict)]))
        for t, k in (("Yangi reklama g'oyalari", "new_creatives"), ("Qilmaslik kerak", "avoid")):
            bl = _bullets(t, d.get(k))
            if bl:
                blocks.append(bl)
        blocks.append({"type": "text", "title": "Boshlang'ich byudjet va test", "text": f"{d.get('start_budget_hint', '')}\n{d.get('test_plan', '')}"})
    else:
        blocks.append({"type": "text", "title": "Hali maslahat yo'q", "text": "Tugmani bosing — AI tahlil asosida qaysi platformaga va qaysi postga reklama berishni aytadi. Kabinetga ulanish shart emas."})
    blocks.append({"type": "actions", "title": "Amallar", "buttons": [ui.btn("Yangi maslahat olish (AI)", "/reklama/maslahat/yangila/", "primary")]})
    return ui.page(request, "Reklama maslahati", blocks, subtitle=b.name, toolbar=[{"label": "Orqaga", "url": "/reklama/"}])
