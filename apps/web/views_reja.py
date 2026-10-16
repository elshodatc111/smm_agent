"""Kontent reja (har platforma uchun alohida) va Karusel ssenariy sahifalari."""
from __future__ import annotations

import json
from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils.html import escape
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.businesses.playbooks import playbook_for
from apps.core.audit import audit
from apps.jobs.queue import enqueue
from apps.studio import carousel as cs
from apps.studio import planner as pl
from apps.studio import services as st
from apps.studio.models import Carousel, ContentPlan

from . import ui
from .common import get_obj

_CTRL = 'style="width:100%"'


def mkform(fields: dict, data=None):
    return type("F", (forms.Form,), fields)(data)


def _need(request):
    if not request.business:
        messages.info(request, "Avval yuqoridan biznesni tanlang.")
        return False
    return True


def _months():
    t = date.today().replace(day=1)
    out = []
    for k in range(4):
        y, m = divmod(t.year * 12 + t.month - 1 + k, 12)
        out.append((f"{y}-{m + 1:02d}", f"{pl.MONTHS_UZ[m + 1].capitalize()} {y}"))
    return out


def _sel(name, options, cur, extra=""):
    return f'<select name="{name}" {extra}>' + "".join(f'<option value="{escape(k)}"{" selected" if k == cur else ""}>{escape(v)}</option>' for k, v in options) + "</select>"


# ======================= KONTENT REJA =======================
@login_required
@require_permission("ai_studio.view")
def reja_home(request):
    if not _need(request):
        return redirect("dashboard")
    b = request.business
    pb = playbook_for(b)
    tname = b.template.name if b.template else "Umumiy"
    prows = [[p["name"], f'{p["share"]}%', p["desc"]] for p in pb["pillars"]]
    month_now = date.today().month
    seas = [f"{pl.MONTHS_UZ[m].capitalize()}: {pb['seasonality'][m]}" for m in sorted(pb["seasonality"]) if m in (month_now, month_now % 12 + 1)]
    blocks = [
        {"type": "text", "title": f"Strategiya: {tname}", "text": "Har ijtimoiy tarmoq uchun ALOHIDA oylik reja tuziladi: ustunlar ulushi, nashr kunlari, format va mavzular shu biznes turiga moslanadi, "
         "AI esa pasportingiz (xizmat, mijoz, narx siyosati, imkoniyat)ga qarab mazmunini yozadi. Kontent tili — faqat o'zbek." + ("\n\nShu oylar uchun mavsum: " + "; ".join(seas) if seas else "")},
        ui.table("Kontent ustunlari (ulush bo'yicha)", ["Ustun", "Ulush", "Nima haqida"], prows),
    ]
    f = mkform({
        "month": forms.ChoiceField(label="Oy", choices=_months()),
        "platforms": forms.MultipleChoiceField(label="Qaysi tarmoqlar uchun (har biriga alohida reja)", choices=pl.PLATFORMS, widget=forms.CheckboxSelectMultiple, initial=["telegram", "instagram", "youtube"]),
        "ppw": forms.IntegerField(label="Haftasiga nechta nashr (bo'sh = avtomatik)", required=False, min_value=1, max_value=7,
                                  help_text="Bo'sh qoldirsangiz pasportdagi «Kontent uchun imkoniyat» va tarmoq odatiga qarab aniqlanadi."),
        "focus": forms.CharField(label="Shu oy uchun alohida e'tibor (ixtiyoriy)", required=False, widget=forms.Textarea(attrs={"rows": 2}),
                                 help_text="Masalan: yangi guruh ochilishi, aksiya, yangi mahsulot."),
    })
    blocks.append(ui.form_block(f, "Yangi oylik reja", "Rejalarni tuzish", action="/reja/yaratish/",
                                intro="Reja darhol tayyor bo'ladi; AI mazmunni biznesingizga moslab to'ldiradi (bir necha daqiqa olishi mumkin)."))
    plans = ContentPlan.objects.filter(business=b).order_by("-month", "platform", "-created_at")[:40]
    rows = []
    for p in plans:
        state = (p.strategy or {}).get("ai_state", "ok")
        rows.append([f"{p.month:%Y-%m}", pl.PLATFORM_UZ.get(p.platform, p.platform), len(p.entries),
                     ui.badge({"pending": "AI yozmoqda…", "fallback": "Andoza", "ok": "AI bilan"}.get(state, state), "running" if state == "pending" else "ok" if state == "ok" else "warn"),
                     ui.badge("Tasdiqlangan" if p.status == "approved" else "Qoralama", "approved" if p.status == "approved" else "draft"),
                     "Yuklangan" if p.loaded_to_calendar else "Yo'q", ui.link("Ochish", f"/reja/{p.pk}/")])
    blocks.append(ui.table("Tuzilgan rejalar", ["Oy", "Tarmoq", "Nashrlar", "Mazmun", "Holat", "Kalendarga", ""], rows, "Hali reja tuzilmagan."))
    return ui.page(request, "Kontent reja", blocks, subtitle=b.name, toolbar=[{"label": "🎠 Karusel ssenariy", "url": "/karusel/"}])


@login_required
@require_POST
@require_permission("ai_studio.create")
def reja_create(request):
    if not _need(request):
        return redirect("dashboard")
    b = request.business
    try:
        y, m = (int(x) for x in request.POST["month"].split("-"))
        month = date(y, m, 1)
    except (KeyError, ValueError):
        messages.error(request, "Oy formati noto'g'ri.")
        return redirect("reja_home")
    plats = [p for p in request.POST.getlist("platforms") if p in pl.PLATFORM_UZ]
    if not plats:
        messages.error(request, "Kamida bitta tarmoqni belgilang.")
        return redirect("reja_home")
    try:
        ppw = int(request.POST.get("ppw") or 0) or None
    except ValueError:
        ppw = None
    made = []
    for plat in plats:
        p = pl.create_plan(b, plat, month, request.user, ppw=ppw, focus=request.POST.get("focus", ""))
        if not p.entries:
            p.strategy = {**p.strategy, "ai_state": "fallback"}
            p.save(update_fields=["strategy"])
        elif not enqueue("plan_fill", {"plan_id": p.pk}, business_id=b.pk, dedupe_key=f"plan_fill:{p.pk}"):
            pass
        made.append(p)
        audit("plan.create", user=request.user, business_id=b.pk, target=f"plan:{p.pk}", detail={"platform": plat, "month": f"{month:%Y-%m}"})
    empty = [pl.PLATFORM_UZ[p.platform] for p in made if not p.entries]
    messages.success(request, f"{len(made)} ta alohida reja tuzildi. AI mazmunni to'ldirmoqda — sahifani biroz keyin yangilang.")
    if empty:
        messages.warning(request, "Bu oyda qolgan nashr kunlari yo'q: " + ", ".join(empty) + ". Keyingi oyni tanlang.")
    return redirect(f"/reja/{made[0].pk}/" if len(made) == 1 else "/reja/")


def _entry_row(p: ContentPlan, i: int, e: dict) -> str:
    fmts = [(k, pl.FORMAT_UZ[k]) for k in pl.PLATFORM_FORMATS[p.platform]]
    occ = f'<div class="muted" style="font-size:12px">🎉 {escape(e["occasion"])}</div>' if e.get("occasion") else ""
    links = []
    if e.get("carousel_id"):
        links.append(f'<a href="/karusel/{e["carousel_id"]}/">🎠 Karusel</a>')
    if e.get("script_id"):
        links.append(f'<a href="/studiya/ssenariy/{e["script_id"]}/">🎬 Ssenariy</a>')
    if e.get("item_id"):
        links.append("✓ kalendarda")
    btns = [f'<button class="btn sm" name="act" value="regen:{i}" title="Shu qatorni AI qayta yozsin">✨</button>']
    if e.get("format") == "carousel":
        btns.append(f'<button class="btn sm" name="act" value="karusel:{i}" title="Karusel ssenariysini yozish">🎠</button>')
    if e.get("format") in ("reel", "short", "video", "story"):
        btns.append(f'<button class="btn sm" name="act" value="ssenariy:{i}" title="Video ssenariysini yozish">🎬</button>')
    btns.append(f'<button class="btn sm" name="act" value="del:{i}" title="O\'chirish" onclick="return confirm(\'Qator o\\\'chirilsinmi?\')">🗑</button>')
    tag = ' <span class="pill">AI</span>' if e.get("source") == "ai" else ""
    return (f'<tr><td>{i + 1}<input type="hidden" name="pillar_{i}" value="{escape(e.get("pillar", ""))}"><input type="hidden" name="pillar_name_{i}" value="{escape(e.get("pillar_name", ""))}">'
            f'<input type="hidden" name="occasion_{i}" value="{escape(e.get("occasion", ""))}"><input type="hidden" name="source_{i}" value="{escape(e.get("source", ""))}">'
            f'<input type="hidden" name="item_id_{i}" value="{e.get("item_id") or ""}"><input type="hidden" name="carousel_id_{i}" value="{e.get("carousel_id") or ""}">'
            f'<input type="hidden" name="script_id_{i}" value="{e.get("script_id") or ""}"></td>'
            f'<td style="min-width:150px"><input type="date" name="date_{i}" value="{escape(e.get("date", ""))}"><input type="time" name="time_{i}" value="{escape(e.get("time", ""))}"><div class="muted" style="font-size:12px">{escape(e.get("weekday", ""))}</div>{occ}</td>'
            f'<td>{_sel(f"format_{i}", fmts, e.get("format", ""))}<div class="muted" style="font-size:12px">{escape(e.get("pillar_name", ""))}{tag}</div></td>'
            f'<td style="min-width:240px"><textarea name="topic_{i}" rows="3" {_CTRL}>{escape(e.get("topic", ""))}</textarea><input name="brief_{i}" placeholder="Dizayner/operator uchun vazifa" value="{escape(e.get("brief", ""))}" {_CTRL}></td>'
            f'<td style="min-width:200px"><textarea name="hook_{i}" rows="2" {_CTRL}>{escape(e.get("hook", ""))}</textarea></td>'
            f'<td style="min-width:150px"><input name="cta_{i}" value="{escape(e.get("cta", ""))}" {_CTRL}><input type="hidden" name="goal_{i}" value="{escape(e.get("goal", ""))}"></td>'
            f'<td style="white-space:nowrap">{"".join(btns)}<div style="font-size:12px;margin-top:4px">{" · ".join(links)}</div></td></tr>')


@login_required
def reja_view(request, pk):
    p = get_obj(request, ContentPlan, pk, "ai_studio.view")
    s = p.strategy or {}
    state = s.get("ai_state", "ok")
    head = {"pending": "⏳ AI mazmunni yozmoqda. Hozircha andoza matnlari ko'rinadi — birozdan keyin sahifani yangilang.",
            "fallback": "⚠ AI hozir javob bermadi — andoza (biznes turiga mos) mavzular turibdi. «AI bilan yangilash» tugmasini bosib qayta urining." + (f" ({s['ai_error']})" if s.get("ai_error") else ""),
            "ok": ""}.get(state, "")
    plat_name = pl.PLATFORM_UZ.get(p.platform, p.platform)
    kv_items = [("Tarmoq", plat_name), ("Oy", f"{pl.MONTHS_UZ[p.month.month].capitalize()} {p.month.year}"), ("Nashrlar", f"{len(p.entries)} ta (haftasiga {s.get('ppw', '—')})"),
                ("Mavsum", s.get("season") or "—"), ("Oy maqsadi", s.get("goal") or "—"), ("Ohang", s.get("tone") or "—")]
    blocks = []
    if head:
        blocks.append({"type": "html", "html": f'<div class="muted">{escape(head)}</div>'})
    blocks.append(ui.kv("Reja", kv_items))
    txt = p.summary + ("\n\nAsosiy xabarlar:\n• " + "\n• ".join(s["key_messages"]) if s.get("key_messages") else "")
    blocks.append({"type": "text", "title": "Strategiya", "text": txt})
    prow = [[x["name"], f'{x["share"]}%', x.get("count", 0)] for x in s.get("pillars", [])]
    blocks.append(ui.table("Ustunlar bo'yicha taqsimot", ["Ustun", "Maqsadli ulush", "Shu oyda nashr"], prow))
    rows = "".join(_entry_row(p, i, e) for i, e in enumerate(p.entries))
    html = (f'<form method="post" action="/reja/{p.pk}/amal/">' + _csrf(request) + f'<input type="hidden" name="n" value="{len(p.entries)}">'
            '<div class="tbl"><table><tr><th>№</th><th>Sana / vaqt</th><th>Format</th><th>Mavzu va vazifa</th><th>Hook</th><th>CTA</th><th></th></tr>'
            + rows + '</table></div><div class="row mt" style="flex-wrap:wrap;gap:8px">'
            '<button class="btn primary" name="act" value="save">💾 Saqlash</button>'
            '<button class="btn" name="act" value="add">➕ Qator qo\'shish</button>'
            '<button class="btn" name="act" value="ai" onclick="this.textContent=\'AI yozmoqda…\'">✨ AI bilan yangilash</button>'
            + ('' if p.status == "approved" else '<button class="btn" name="act" value="approve">✔ Tasdiqlash</button>')
            + '<button class="btn" name="act" value="load">📅 Kalendarga qoralama qilib yuklash</button>'
            '<button class="btn" name="act" value="delete_plan" onclick="return confirm(\'Butun reja o\\\'chirilsinmi?\')">🗑 Rejani o\'chirish</button></div></form>')
    blocks.append({"type": "html", "title": "Reja (tahrirlash mumkin)", "html": html})
    return ui.page(request, f"{plat_name} · {pl.MONTHS_UZ[p.month.month]} {p.month.year}", blocks, subtitle=("Tasdiqlangan" if p.status == "approved" else "Qoralama"),
                   toolbar=[{"label": "← Barcha rejalar", "url": "/reja/"}])


def _csrf(request):
    from django.middleware.csrf import get_token
    return f'<input type="hidden" name="csrfmiddlewaretoken" value="{get_token(request)}">'


def _read_entries(p: ContentPlan, post) -> list[dict]:
    out = []
    try:
        n = int(post.get("n") or 0)
    except ValueError:
        n = 0
    for i in range(n):
        if f"date_{i}" not in post:
            continue
        e = {k: post.get(f"{k}_{i}", "") for k in ("date", "time", "format", "topic", "hook", "cta", "goal", "brief", "pillar", "pillar_name", "occasion", "source")}
        for k in ("item_id", "carousel_id", "script_id"):
            v = post.get(f"{k}_{i}", "")
            e[k] = int(v) if str(v).isdigit() else None
        out.append(pl.validate_entry(p.platform, e))
    return out


@login_required
@require_POST
def reja_action(request, pk):
    p = get_obj(request, ContentPlan, pk, "ai_studio.create")
    act = request.POST.get("act", "save")
    b = p.business
    if act == "delete_plan":
        p.delete()
        messages.success(request, "Reja o'chirildi.")
        return redirect("reja_home")
    ents = _read_entries(p, request.POST)
    if ents or "n" in request.POST:
        p.entries = ents
    kind, _, arg = act.partition(":")
    idx = int(arg) if arg.isdigit() else None
    if kind == "del" and idx is not None and 0 <= idx < len(p.entries):
        p.entries.pop(idx)
        messages.success(request, "Qator o'chirildi.")
    elif kind == "add":
        last = p.entries[-1] if p.entries else {}
        base = date.fromisoformat(last["date"]) if last.get("date") else p.month
        p.entries.append(pl.validate_entry(p.platform, {"date": base.isoformat(), "time": last.get("time", ""), "format": pl.PLATFORM_FORMATS[p.platform][0],
                                                       "topic": "Yangi mavzu", "pillar_name": "Qo'shimcha", "source": "qo'lda"}))
        messages.success(request, "Bo'sh qator qo'shildi.")
    elif kind == "approve":
        p.status = "approved"
        messages.success(request, "Reja tasdiqlandi. Endi kalendarga yuklashingiz mumkin.")
    p.entries.sort(key=lambda e: (e.get("date") or "9999", e.get("time") or ""))
    p.save()
    # tartiblangach indekslar o'zgargan bo'lishi mumkin: AI amallari uchun mavzu bo'yicha qayta topamiz
    if kind in ("regen", "karusel", "ssenariy") and idx is not None:
        try:
            posted_topic = request.POST.get(f"topic_{idx}", "")
            idx = next(i for i, e in enumerate(p.entries) if e.get("topic") == posted_topic.strip()[:200])
        except StopIteration:
            idx = None
    if kind == "regen" and idx is not None:
        pl.regenerate_entry(p, idx, request.user)
        messages.success(request, "Qator qayta yozildi (AI ishlamasa — andozadan yangi g'oya).")
    elif kind == "ai":
        n = pl.fill_with_ai(p, request.user)
        (messages.success if n else messages.warning)(request, f"AI {n} ta qatorni yangiladi." if n else "AI hozir javob bermadi yoki barcha mavzular takror edi. Kalitlarni tekshiring.")
    elif kind == "karusel" and idx is not None:
        e = p.entries[idx]
        try:
            c = cs.generate_carousel(b, e.get("topic", ""), platform=p.platform if p.platform in ("instagram", "telegram") else "instagram", user=request.user,
                                     plan=p, plan_entry=idx, extra=f"Hook g'oyasi: {e.get('hook', '')}")
            e["carousel_id"] = c.pk
            p.save(update_fields=["entries"])
            return redirect(f"/karusel/{c.pk}/")
        except Exception as ex:  # noqa: BLE001
            messages.error(request, getattr(ex, "user_message_uz", None) or f"Karusel yozilmadi: {ex}")
    elif kind == "ssenariy" and idx is not None:
        e = p.entries[idx]
        fmt = "long" if (e.get("format") == "video" and p.platform == "youtube") else ("stories" if e.get("format") == "story" else "reel")
        try:
            sc = st.generate_script(b, f"{e.get('topic', '')}. Hook g'oyasi: {e.get('hook', '')}. Maqsad: {e.get('goal', '')}", fmt, 2, request.user)
            e["script_id"] = sc.pk
            p.save(update_fields=["entries"])
            return redirect(f"/studiya/ssenariy/{sc.pk}/")
        except Exception as ex:  # noqa: BLE001
            messages.error(request, getattr(ex, "user_message_uz", None) or f"Ssenariy yozilmadi: {ex}")
    elif kind == "load":
        from apps.accounts.services import perms
        if not perms.can(request.user, "calendar.create", b):
            messages.error(request, "Kalendarga yuklash uchun ruxsat yo'q.")
        else:
            n = pl.load_to_calendar(p, request.user)
            messages.success(request, f"{n} ta qoralama kalendarga yuklandi (AI qoralamasi: nashrdan oldin inson ko'rib chiqadi)." if n else "Yuklanadigan yangi qator yo'q.")
            return redirect("calendar")
    elif kind == "save":
        messages.success(request, "Saqlandi.")
    return redirect(f"/reja/{p.pk}/")


# Eski havolalar uchun
@login_required
def studio_plan_redirect(request, pk=None):
    return redirect(f"/reja/{pk}/" if pk else "/reja/")


# ======================= KARUSEL SSENARIY =======================
def _angle_choices(b):
    return [("", "Avtomatik (hikoyaga qarab)")] + [(a["name"], f"{a['name']}  ({' → '.join(a['arc'][:4])}…)") for a in playbook_for(b)["angles"]]


@login_required
@require_permission("ai_studio.view")
def carousel_home(request):
    if not _need(request):
        return redirect("dashboard")
    b = request.business
    pb = playbook_for(b)
    f = mkform({
        "topic": forms.CharField(label="Karusel mavzusi", widget=forms.Textarea(attrs={"rows": 2}), help_text="Masalan: «Mijoz birinchi marta kelgandan natijagacha». Mavzu aniq bo'lsa, hikoya ham aniq chiqadi."),
        "size": forms.ChoiceField(label="Hajmi", choices=cs.SIZES, initial="auto", help_text="Slayd soni qotirilmagan. Ko'p bo'lsa avtomatik 1-qism, 2-qism… ga bo'linadi (har qismda ko'pi bilan 10 ta)."),
        "angle": forms.ChoiceField(label="Hikoya yo'li", choices=_angle_choices(b), required=False),
        "platform": forms.ChoiceField(label="Tarmoq", choices=[("instagram", "Instagram"), ("telegram", "Telegram")]),
        "extra": forms.CharField(label="Qo'shimcha istak (ixtiyoriy)", required=False, widget=forms.Textarea(attrs={"rows": 2})),
    })
    ideas = [x for x in pb["ideas"] if x["format"] == "carousel"][:6]
    sug = "".join(f'<form method="post" action="/karusel/yaratish/" style="display:inline">{_csrf(request)}<input type="hidden" name="topic" value="{escape(x["topic"])}">'
                  f'<input type="hidden" name="size" value="auto"><input type="hidden" name="platform" value="instagram"><button class="btn sm" style="margin:3px">{escape(x["topic"])}</button></form>' for x in ideas)
    blocks = [ui.form_block(f, "Yangi karusel ssenariy", "Ssenariyni yozish", action="/karusel/yaratish/",
                            intro="Biznesingizga asoslangan kichik hikoya: har slaydda juda qisqa matn va dizayner uchun vizual vazifa. AI 30–60 soniya ishlashi mumkin.")]
    if sug:
        blocks.append({"type": "html", "title": f"{b.template.name if b.template else 'Biznes'} uchun tayyor mavzular (bir bosishda)", "html": sug})
    rows = [[ui.link(c.title, f"/karusel/{c.pk}/"), len(c.slides), f"{len(c.parts)} qism", c.get_status_display(), ui.dt(c.created_at)] for c in Carousel.objects.filter(business=b)[:30]]
    blocks.append(ui.table("Tayyor ssenariylar", ["Nomi", "Slaydlar", "Postlar", "Holat", "Sana"], rows, "Hali karusel ssenariy yo'q."))
    return ui.page(request, "Karusel ssenariy", blocks, subtitle=b.name, toolbar=[{"label": "📅 Kontent reja", "url": "/reja/"}])


@login_required
@require_POST
@require_permission("ai_studio.create")
def carousel_create(request):
    if not _need(request):
        return redirect("dashboard")
    size = request.POST.get("size", "auto")
    try:
        c = cs.generate_carousel(request.business, request.POST.get("topic", ""), size=size if size in dict(cs.SIZES) else "auto", angle=request.POST.get("angle", ""),
                                 extra=request.POST.get("extra", ""), platform=request.POST.get("platform", "instagram"), user=request.user)
    except Exception as ex:  # noqa: BLE001
        messages.error(request, getattr(ex, "user_message_uz", None) or f"Karusel yozilmadi: {ex}")
        return redirect("carousel_home")
    if (c.story or {}).get("source") == "andoza":
        messages.warning(request, "AI hozir javob bermadi — andoza skelet qo'yildi. Matnlarni to'ldiring yoki «Qayta yozish» ni bosing.")
    else:
        messages.success(request, f"Ssenariy tayyor: {len(c.slides)} ta slayd, {len(c.parts)} ta post.")
    audit("carousel.create", user=request.user, business_id=request.business.pk, target=f"carousel:{c.pk}", detail={"slides": len(c.slides)})
    return redirect(f"/karusel/{c.pk}/")


def _slide_rows(c: Carousel, part: dict) -> str:
    rows = []
    for s in cs.part_slides(c, part):
        n = s["n"]
        rows.append(
            f'<tr><td><b>{n}</b><input type="hidden" name="role_{n}" value="{escape(s["role"])}"></td>'
            f'<td style="white-space:nowrap">{escape(cs.ROLE_UZ.get(s["role"], s["role"] or "—"))}</td>'
            f'<td style="min-width:180px"><input name="title_{n}" value="{escape(s["title"])}" {_CTRL}><textarea name="text_{n}" rows="2" {_CTRL}>{escape(s["text"])}</textarea></td>'
            f'<td style="min-width:220px"><textarea name="visual_{n}" rows="3" {_CTRL}>{escape(s["visual"])}</textarea><input type="hidden" name="note_{n}" value="{escape(s.get("note", ""))}">'
            f'{"<div class=muted style=font-size:12px>" + escape(s["note"]) + "</div>" if s.get("note") else ""}</td>'
            f'<td style="white-space:nowrap"><button class="btn sm" name="act" value="regen:{n}" title="Slaydni qisqaroq/boshqacha yozish">✨</button>'
            f'<button class="btn sm" name="act" value="addafter:{n}" title="Pastiga slayd qo\'shish">➕</button>'
            f'<button class="btn sm" name="act" value="del:{n}" title="O\'chirish" onclick="return confirm(\'Slayd o\\\'chirilsinmi?\')">🗑</button></td></tr>')
    return "".join(rows)


@login_required
def carousel_view(request, pk):
    c = get_obj(request, Carousel, pk, "ai_studio.view")
    sty = c.story or {}
    items = [("Hikoya", sty.get("logline") or c.topic), ("Qahramon", sty.get("hero") or "—"), ("Hikoya yo'li", c.angle or "—"),
             ("Jami", f"{len(c.slides)} slayd → {len(c.parts)} ta post"), ("Nega shuncha slayd", sty.get("size_reason") or "—"), ("Dizayn uslubi", cs.style_text(c) or "—")]
    blocks = [ui.kv(c.title, items)]
    if sty.get("source") == "andoza":
        blocks.append({"type": "html", "html": '<div class="muted">⚠ Bu AI yozmagan andoza skelet. [to\'ldiring] joylarini to\'ldiring yoki «Qayta yozish»ni bosing.</div>'})
    form_open = f'<form method="post" action="/karusel/{c.pk}/amal/">{_csrf(request)}<input type="hidden" name="total" value="{len(c.slides)}">'
    body = form_open
    for part in c.parts:
        k = part["n"]
        copy_id = f"cp{k}"
        txt = cs.part_text(c, part)
        status = f'✓ kalendarda (#{part["item_id"]})' if part.get("item_id") else f'<button class="btn sm" name="act" value="load:{k}">📅 Kalendarga qoralama</button>'
        body += (f'<h3 style="margin:16px 0 4px">{escape(part["title"])} <span class="muted" style="font-size:13px">· {len(part["slides"])} slayd · nashr: {escape(part["when"])}</span></h3>'
                 f'<div class="tbl"><table><tr><th>№</th><th>Rol</th><th>Matn</th><th>Vizual vazifa</th><th></th></tr>{_slide_rows(c, part)}</table></div>'
                 + (f'<div class="muted" style="font-size:13px">Belgi (1-slayd): {escape(part["overlay_first"])}</div>' if part.get("overlay_first") else "")
                 + (f'<div class="muted" style="font-size:13px">Belgi (oxirgi slayd): {escape(part["overlay_last"])}</div>' if part.get("overlay_last") else "")
                 + f'<textarea id="{copy_id}" style="position:absolute;left:-9999px">{escape(txt)}</textarea>'
                 f'<div style="margin-top:6px"><b>Post matni:</b><div style="white-space:pre-wrap">{escape(part["caption"])}</div><div class="muted">{escape(" ".join(part.get("hashtags", [])))}</div></div>'
                 f'<div class="row mt" style="gap:8px;flex-wrap:wrap"><button type="button" class="btn sm" onclick="var t=document.getElementById(\'{copy_id}\').value;'
                 f'(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>{{this.textContent=\'✓ Nusxalandi\'}},()=>{{window.prompt(\'Nusxa oling:\',t)}})">📋 Dizayner uchun nusxa</button>{status}</div><hr>')
    body += ('<div class="row mt" style="gap:8px;flex-wrap:wrap"><button class="btn primary" name="act" value="save">💾 Saqlash va qayta bo\'lish</button>'
             '<input name="instruction" placeholder="Qayta yozish uchun istak (masalan: qisqaroq)" style="min-width:260px">'
             '<button class="btn" name="act" value="rewrite" onclick="return confirm(\'Butun ssenariy qayta yoziladi. Davom etasizmi?\')">🔄 Butunlay qayta yozish</button>'
             '<button class="btn" name="act" value="ready">✔ Tayyor deb belgilash</button>'
             '<button class="btn" name="act" value="delete" onclick="return confirm(\'Ssenariy o\\\'chirilsinmi?\')">🗑 O\'chirish</button></div></form>')
    blocks.append({"type": "html", "title": "Slaydlar (tahrirlash mumkin)", "html": body})
    return ui.page(request, "Karusel ssenariy", blocks, subtitle=f"{c.business.name} · {pl.PLATFORM_UZ.get(c.platform, c.platform)}", toolbar=[{"label": "← Barcha ssenariylar", "url": "/karusel/"}])


@login_required
@require_POST
def carousel_action(request, pk):
    c = get_obj(request, Carousel, pk, "ai_studio.create")
    act = request.POST.get("act", "save")
    if act == "delete":
        c.delete()
        messages.success(request, "O'chirildi.")
        return redirect("carousel_home")
    P = request.POST
    # formadagi (ko'rinib turgan) slaydlarni o'qiymiz; ko'rinmaganlari (boshqa qismdagilar) ham shu formada bor
    new = []
    for s in c.slides:
        n = s["n"]
        if f"title_{n}" in P:
            s = {**s, "title": P.get(f"title_{n}", ""), "text": P.get(f"text_{n}", ""), "visual": P.get(f"visual_{n}", ""), "note": P.get(f"note_{n}", s.get("note", ""))}
        new.append(s)
    c.slides = cs.clean_slides(new)
    kind, _, arg = act.partition(":")
    n = int(arg) if arg.isdigit() else None
    if kind == "del" and n and 1 <= n <= len(c.slides):
        if len(c.slides) <= cs.MIN_SLIDES:
            messages.error(request, f"Kamida {cs.MIN_SLIDES} ta slayd bo'lishi kerak.")
        else:
            c.slides.pop(n - 1)
    elif kind == "addafter" and n and 1 <= n <= len(c.slides):
        if len(c.slides) >= cs.MAX_SLIDES:
            messages.error(request, f"Ko'pi bilan {cs.MAX_SLIDES} ta slayd.")
        else:
            c.slides.insert(n, {"role": "maslahat", "title": "Yangi slayd", "text": "[to'ldiring]", "visual": "", "note": "", "n": n + 1})
    elif kind == "regen" and n:
        c.save(update_fields=["slides"])
        ok = cs.regen_slide(c, n, P.get("instruction", ""), request.user)
        (messages.success if ok else messages.warning)(request, f"{n}-slayd qayta yozildi." if ok else "AI hozir javob bermadi.")
        c.refresh_from_db()
    elif kind == "rewrite":
        try:
            nc = cs.generate_carousel(c.business, c.topic or c.title, extra=P.get("instruction", ""), platform=c.platform, user=request.user, plan=c.plan, plan_entry=c.plan_entry)
            return redirect(f"/karusel/{nc.pk}/")
        except Exception as ex:  # noqa: BLE001
            messages.error(request, getattr(ex, "user_message_uz", None) or f"Xato: {ex}")
    elif kind == "ready":
        c.status = "ready"
        messages.success(request, "Tayyor deb belgilandi.")
    keep = {p["n"]: p for p in c.parts}
    cs.rebuild_parts(c)
    for p in c.parts:  # qayta bo'lishda kalendarga yuklangan qism belgisini saqlab qolamiz
        old = keep.get(p["n"])
        if old:
            p["item_id"] = old.get("item_id")
            p["hashtags"] = old.get("hashtags", p["hashtags"])
    c.save()
    if kind == "load" and n:
        from apps.accounts.services import perms
        if not perms.can(request.user, "calendar.create", c.business):
            messages.error(request, "Kalendarga yuklash uchun ruxsat yo'q.")
        else:
            item = cs.load_part_to_calendar(c, n, request.user)
            if item:
                messages.success(request, f"{n}-qism kalendarga qoralama karusel post qilib yuklandi. Rasmlarni dizayner tayyorlagach, postga qo'shing.")
            else:
                messages.info(request, "Bu qism allaqachon kalendarda.")
    elif kind == "save":
        messages.success(request, f"Saqlandi: {len(c.slides)} slayd → {len(c.parts)} ta post.")
    return redirect(f"/karusel/{c.pk}/")
