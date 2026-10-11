"""O'sish bo'limlari: G'oyalar banki, Lidlar, Kunlik statistika, Aqlli ogohlantirishlar."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.core import alerts
from apps.core.audit import audit
from apps.core.utils import fmt_dt, tz
from apps.metrics import daily
from apps.metrics.models import DailyStat, Lead
from apps.studio import ideas as idea_svc
from apps.studio.models import Idea
from . import ui
from .common import get_obj

FMT_TO_TYPE = {"post": "image", "reel": "reel", "short": "short", "video": "video", "story": "story", "carousel": "carousel"}
SRC_UZ = {"competitor": "Raqobatchi tahlili", "own": "O'z tahlilingiz", "auto": "Doimiy g'oya", "manual": "Qo'lda"}


def _biz_ids(request, code):
    return [request.business.pk] if request.business else list(perms.businesses_for(request.user, code).values_list("pk", flat=True))


# ===================================================================== G'OYALAR BANKI
@login_required
@require_permission("ai_studio.view")
def ideas_home(request):
    ids = _biz_ids(request, "ai_studio.view")
    st = request.GET.get("s", "")
    qs = Idea.objects.filter(business_id__in=ids).select_related("business")
    if st in ("new", "saved", "used", "rejected"):
        qs = qs.filter(status=st)
    else:
        qs = qs.exclude(status="rejected")
    tabs = "".join(f'<a class="pill" style="{"background:#2563eb;color:#fff" if st == k else ""}" href="?s={k}">{v}</a> ' for k, v in (("", "Faol"), ("new", "Yangi"), ("saved", "Saqlangan"), ("used", "Ishlatilgan"), ("rejected", "Rad etilgan")))
    rows = []
    for i in qs[:80]:
        rows.append([ui.dt(i.day) if False else i.day.strftime("%d.%m.%Y"), ui.link(i.title, f"/goyalar/{i.pk}/", (i.hook or "")[:90]), i.business.name, (i.platform or "—").title(),
                     idea_svc.FMT_UZ.get(i.fmt, i.fmt or "—"), SRC_UZ.get(i.source, i.source), ui.badge(i.get_status_display(), {"new": "pending", "saved": "approved", "used": "ok", "rejected": "failed"}.get(i.status))])
    tb = []
    if request.business and perms.can(request.user, "ai_studio.create", request.business):
        tb = [{"label": "✨ Hozir yangi g'oya", "post": "/goyalar/yaratish/", "cls": "primary"}]
    blocks = [{"type": "html", "html": tabs}, ui.table(None, ["Sana", "G'oya", "Biznes", "Platforma", "Format", "Manba", "Holat"], rows, empty="Hali g'oya yo'q. Har kuni ertalab tahlildan avtomatik qo'shiladi; «Hozir yangi g'oya» tugmasi bilan ham olasiz.")]
    return ui.page(request, "G'oyalar banki", blocks, subtitle="Raqobatchi va o'z tahlilingizdan chiqqan g'oyalar — har birida tayyor rejissyor ssenariysi", toolbar=tb)


@login_required
@require_POST
@require_permission("ai_studio.create")
def ideas_generate(request):
    if not request.business:
        messages.info(request, "Avval biznesni tanlang.")
        return redirect("ideas_home")
    new = idea_svc.generate_for_business(request.business, 1)
    messages.success(request, f"{len(new)} ta yangi g'oya qo'shildi." if new else "G'oya yaratilmadi.")
    audit("idea.generate", user=request.user, business_id=request.business.pk)
    return redirect(f"/goyalar/{new[0].pk}/" if new else "/goyalar/")


@login_required
@require_permission("ai_studio.view")
def idea_detail(request, pk):
    i = get_obj(request, Idea, pk, "ai_studio.view")
    can_c = perms.can(request.user, "ai_studio.create", i.business)
    ref = i.source_ref or {}
    src = []
    if ref.get("competitor"):
        src.append(("Raqobatchi", f"{ref['competitor']}" + (f" · {ref.get('views')} ko'rish" if ref.get("views") else "") + (f" · {ref.get('likes')} layk" if ref.get("likes") else "")))
    if ref.get("text"):
        src.append(("Asos bo'lgan post", ref["text"]))
    if ref.get("own_text"):
        src.append(("O'z posti", ref["own_text"]))
    blocks = [ui.kv(i.title, [("Biznes", i.business.name), ("Platforma / format", f"{(i.platform or '—').title()} · {idea_svc.FMT_UZ.get(i.fmt, i.fmt or '—')}"), ("Manba", SRC_UZ.get(i.source, i.source)),
                              ("Holat", i.get_status_display()), ("Kun", i.day.strftime("%d.%m.%Y")), ("Hook (birinchi jumla)", i.hook), ("G'oya mohiyati", i.angle), ("Nega aynan shu?", i.why)] + src)]
    acts = []
    if perms.can(request.user, "calendar.create", i.business) and i.status != "used":
        acts.append(ui.btn("📝 Postga aylantirish", f"/goyalar/{i.pk}/post/", "primary"))
    if i.content_item_id:
        acts.append({"t": "Yaratilgan postni ochish", "label": "Yaratilgan postni ochish", "post": "", "u": f"/kalendar/{i.content_item_id}/"})
    if can_c:
        if i.status != "saved":
            acts.append(ui.btn("⭐ Saqlash", f"/goyalar/{i.pk}/holat/saved/"))
        if i.status != "rejected":
            acts.append(ui.btn("✖ Rad etish", f"/goyalar/{i.pk}/holat/rejected/", "danger"))
        else:
            acts.append(ui.btn("↩ Qaytarish", f"/goyalar/{i.pk}/holat/new/"))
        acts.append(ui.btn("🎬 AI bilan to'liq ssenariy", f"/goyalar/{i.pk}/ssenariy/", "blue"))
    blocks.append({"type": "actions", "title": "Amallar", "buttons": [a for a in acts if a.get("post")]})
    body = i.script or {}
    if body.get("scenes"):
        blocks.append({"type": "html", "title": "🎬 Rejissyor ssenariysi", "html": _script_html(body)})
    elif i.script_text:
        blocks.append({"type": "text", "title": "🎬 Ssenariy", "text": i.script_text})
    return ui.page(request, "G'oya", blocks, subtitle=i.title)


def _script_html(b: dict) -> str:
    from html import escape as e
    h = [f"<p><b>G'oya:</b> {e(str(b.get('concept', '')))}</p>"]
    hv = b.get("hook_variants") or []
    if hv:
        h.append("<p><b>Hook variantlari:</b> " + " | ".join(e(str(x)) for x in hv) + "</p>")
    h.append(f"<p class='muted'>Davomiyligi: {e(str(b.get('duration_sec') or '—'))} s · Joy: {e(str(b.get('location', '—')))}</p>")
    for c in b.get("cast") or []:
        if isinstance(c, dict):
            h.append(f"<div>👤 <b>{e(str(c.get('role', '')))}</b> — {e(str(c.get('look', '')))} <span class='muted'>{e(str(c.get('note', '')))}</span></div>")
    if b.get("equipment"):
        h.append("<p>🎒 <b>Jihoz:</b> " + "; ".join(e(str(x)) for x in b["equipment"]) + "</p>")
    au = b.get("audio") or {}
    if au:
        h.append(f"<p>🎧 <b>Ovoz:</b> {e(str(au.get('voice_style', '')))} · <b>Musiqa:</b> {e(str(au.get('music_mood', '')))}</p>")
    h.append("<div class='tbl'><table><tr><th>#</th><th>Vaqt</th><th>Kadr / kamera</th><th>Aktyor</th><th>Matn / ekran</th></tr>")
    for s in b.get("scenes") or []:
        cam = s.get("camera") or {}
        act = s.get("actor") or {}
        h.append("<tr><td>%s</td><td>%s</td><td><b>%s</b><br>%s<br><span class='muted'>%s · %s</span></td><td>%s<br><span class='muted'>%s</span><br><i>%s</i></td><td>%s<br><span class='muted'>%s</span></td></tr>" % tuple(
            e(str(x)) for x in (s.get("n", ""), s.get("t", ""), s.get("shot_type", ""), cam.get("position", ""), cam.get("angle", ""), cam.get("movement", ""),
                                act.get("action", ""), act.get("emotion", ""), act.get("line", ""), s.get("voiceover", "") or s.get("on_screen_text", ""), s.get("transition", ""))))
    h.append("</table></div>")
    if b.get("cta"):
        h.append(f"<p>📣 <b>CTA:</b> {e(str(b['cta']))}</p>")
    if b.get("editing_notes"):
        h.append("<p>✂ <b>Montaj:</b> " + "; ".join(e(str(x)) for x in b["editing_notes"]) + "</p>")
    if b.get("checklist"):
        h.append("<p>☑ <b>Tekshiruv:</b> " + "; ".join(e(str(x)) for x in b["checklist"]) + "</p>")
    if b.get("notes"):
        h.append(f"<p class='muted'>{e(str(b['notes']))}</p>")
    return "".join(h)


@login_required
@require_POST
def idea_status(request, pk, new):
    i = get_obj(request, Idea, pk, "ai_studio.create")
    if new in ("new", "saved", "rejected", "used"):
        i.status = new
        i.save(update_fields=["status"])
        audit("idea.status", user=request.user, business_id=i.business_id, target=f"idea:{i.pk}", detail={"title": i.title, "status": new})
    return redirect("idea_detail", pk=i.pk)


@login_required
@require_POST
def idea_script(request, pk):
    i = get_obj(request, Idea, pk, "ai_studio.create")
    idea_svc.make_script(i, use_ai=True, user=request.user)
    ok = getattr(i, "ai_script", False)
    (messages.success if ok else messages.warning)(request, "AI ssenariysi yozildi." if ok else "AI hozir mavjud emas — andoza ssenariy qo'yildi. AI kalitlarini tekshirib, qayta urining.")
    return redirect("idea_detail", pk=i.pk)


@login_required
@require_POST
def idea_to_post(request, pk):
    from apps.connections.models import SocialAccount
    from apps.content.models import ContentItem, ContentTarget
    i = get_obj(request, Idea, pk, "calendar.create", business_field="business")
    text = (i.hook + "\n\n" if i.hook else "") + (i.angle or "")
    item = ContentItem.objects.create(business=i.business, title=i.title[:200], text=text.strip(), media_type=FMT_TO_TYPE.get(i.fmt, "image"), status="draft",
                                      created_by=request.user, hook_idea=i.hook[:300], notes=("G'oya banki\n\n" + (i.script_text or ""))[:20000], brief=(i.angle or "")[:1000])
    for a in SocialAccount.objects.filter(business=i.business, platform=i.platform, archived_at__isnull=True)[:1]:
        ContentTarget.objects.get_or_create(item=item, account=a)
    i.content_item, i.status = item, "used"
    i.save(update_fields=["content_item", "status"])
    audit("idea.to_post", user=request.user, business_id=i.business_id, target=f"item:{item.pk}", detail={"title": i.title})
    messages.success(request, "Qoralama yaratildi. Matn, fayl va vaqtni to'ldiring — ssenariy «Ichki izoh» da.")
    return redirect("content_edit", pk=item.pk)


# ===================================================================== LIDLAR
class LeadForm(forms.Form):
    name = forms.CharField(label="Ism", required=False, max_length=160)
    phone = forms.CharField(label="Telefon", required=False, max_length=40)
    source = forms.ChoiceField(label="Manba", choices=Lead.SOURCES)
    amount = forms.IntegerField(label="Sotuv summasi (so'm, ixtiyoriy)", required=False, min_value=0)
    note = forms.CharField(label="Izoh", required=False, max_length=400)
    when = forms.DateField(label="Sana (bo'sh = bugun)", required=False, widget=forms.DateInput(attrs={"type": "date"}))


@login_required
@require_permission("analytics.view")
def leads_home(request):
    ids = _biz_ids(request, "analytics.view")
    qs = Lead.objects.filter(business_id__in=ids).select_related("business", "content_item")
    can_add = bool(request.business) and perms.can(request.user, "links.create", request.business)
    now = timezone.now()
    n30 = qs.filter(created_at__gte=now - timedelta(days=30)).count()
    n7 = qs.filter(created_at__gte=now - timedelta(days=7)).count()
    won = qs.filter(status="won")
    s = sum(x.amount or 0 for x in won)
    blocks = [ui.kv("Qisqacha", [("Jami lid", qs.count()), ("So'nggi 7 kun", n7), ("So'nggi 30 kun", n30), ("Sotuv bo'lgan", won.count()), ("Sotuv summasi", f"{int(s):,} so'm".replace(",", " "))])]
    by_src = {}
    for x in qs.filter(created_at__gte=now - timedelta(days=30)):
        by_src[x.get_source_display()] = by_src.get(x.get_source_display(), 0) + 1
    if by_src:
        blocks.append(ui.table("Manbalar (30 kun)", ["Manba", "Soni"], [[k, v] for k, v in sorted(by_src.items(), key=lambda t: -t[1])]))
    rows = []
    for x in qs[:150]:
        acts = [ui.btn(lbl, f"/lidlar/{x.pk}/holat/{k}/", "sm") for k, lbl in (("contacted", "Aloqa"), ("won", "Sotuv"), ("lost", "Yo'q")) if x.status != k] if can_add else []
        rows.append([x.created_at.astimezone(tz()).strftime("%d.%m.%Y"), x.name or "—", x.phone or "—", x.get_source_display(), x.business.name if not request.business else (ui.link(x.content_item.title or "post", f"/kalendar/{x.content_item_id}/") if x.content_item_id else "—"),
                     ui.badge(x.get_status_display(), {"new": "pending", "contacted": "approved", "won": "ok", "lost": "failed"}.get(x.status)), (f"{int(x.amount):,}".replace(",", " ") if x.amount else "—"), acts[0] if acts else "—", acts[1] if len(acts) > 1 else "—"])
    blocks.append(ui.table("Lidlar ro'yxati", ["Sana", "Ism", "Telefon", "Manba", "Biznes / post", "Holat", "Summa", "", ""], rows, empty="Hali lid kiritilmagan."))
    if can_add:
        blocks.append(ui.form_block(LeadForm(), "Lid qo'shish", "Qo'shish", action="/lidlar/qoshish/"))
        blocks.append({"type": "html", "title": "Excel/CSV'dan yuklash", "html": '<form method="post" action="/lidlar/import/" enctype="multipart/form-data">' + _csrf_input(request) + '<input type="file" name="file" accept=".csv" required> <button class="btn">Yuklash</button></form><div class="hint">Ustunlar: ism, telefon, manba, summa, izoh, sana (YYYY-MM-DD). Birinchi qator — sarlavha.</div>'})
    tb = [{"label": "⬇ CSV", "url": "/lidlar/eksport/", "cls": ""}] if perms.can(request.user, "analytics.export", request.business) or request.user.is_admin else []
    return ui.page(request, "Lidlar", blocks, subtitle="Kontentdan kelgan arizalar — kunlik statistikaga avtomatik qo'shiladi", toolbar=tb)


def _csrf_input(request) -> str:
    from django.middleware.csrf import get_token
    return f'<input type="hidden" name="csrfmiddlewaretoken" value="{get_token(request)}">'


@login_required
@require_POST
def lead_add(request):
    if not request.business or not perms.can(request.user, "links.create", request.business):
        messages.error(request, "Avval biznesni tanlang (yoki ruxsat yo'q).")
        return redirect("leads_home")
    f = LeadForm(request.POST)
    if f.is_valid():
        d = f.cleaned_data
        when = datetime.combine(d["when"], datetime.min.time().replace(hour=12), tzinfo=tz()) if d.get("when") else timezone.now()
        l = Lead.objects.create(business=request.business, name=d["name"], phone=d["phone"], source=d["source"], note=d["note"], amount=d.get("amount"), created_by=request.user, created_at=when)
        audit("lead.add", user=request.user, business_id=l.business_id, target=f"lead:{l.pk}", detail={"name": l.name})
        messages.success(request, "Lid qo'shildi.")
    else:
        messages.error(request, "Ma'lumot noto'g'ri: " + "; ".join(sum((list(v) for v in f.errors.values()), [])))
    return redirect("leads_home")


@login_required
@require_POST
def lead_status(request, pk, new):
    l = get_obj(request, Lead, pk, "links.create")
    if new in dict(Lead.STATUS):
        l.status = new
        l.save(update_fields=["status"])
        audit("lead.update", user=request.user, business_id=l.business_id, target=f"lead:{l.pk}", detail={"status": new})
    return redirect("leads_home")


@login_required
@require_POST
def lead_import(request):
    if not request.business or not perms.can(request.user, "links.create", request.business):
        messages.error(request, "Avval biznesni tanlang.")
        return redirect("leads_home")
    f = request.FILES.get("file")
    if not f:
        return redirect("leads_home")
    raw = f.read().decode("utf-8-sig", errors="replace")
    rd = csv.reader(io.StringIO(raw), delimiter=";" if raw.count(";") > raw.count(",") else ",")
    next(rd, None)
    n = 0
    srcs = {v.lower(): k for k, v in Lead.SOURCES}
    srcs.update({k: k for k, _ in Lead.SOURCES})
    for r in rd:
        r = [c.strip() for c in r] + [""] * 6
        if not (r[0] or r[1]):
            continue
        try:
            when = datetime.combine(date.fromisoformat(r[5]), datetime.min.time().replace(hour=12), tzinfo=tz()) if r[5] else timezone.now()
        except ValueError:
            when = timezone.now()
        amt = int(r[3].replace(" ", "")) if r[3].replace(" ", "").isdigit() else None
        Lead.objects.create(business=request.business, name=r[0][:160], phone=r[1][:40], source=srcs.get(r[2].lower(), "other"), amount=amt, note=r[4][:400], created_by=request.user, created_at=when)
        n += 1
    audit("lead.add", user=request.user, business_id=request.business.pk, detail={"import": n})
    messages.success(request, f"{n} ta lid yuklandi.")
    return redirect("leads_home")


@login_required
@require_permission("analytics.export")
def leads_export(request):
    ids = _biz_ids(request, "analytics.export")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["sana", "biznes", "ism", "telefon", "manba", "holat", "summa", "izoh"])
    for x in Lead.objects.filter(business_id__in=ids).select_related("business"):
        w.writerow([x.created_at.astimezone(tz()).strftime("%Y-%m-%d"), x.business.name, x.name, x.phone, x.get_source_display(), x.get_status_display(), x.amount or "", x.note])
    r = HttpResponse("﻿" + out.getvalue(), content_type="text/csv; charset=utf-8")
    r["Content-Disposition"] = 'attachment; filename="lidlar.csv"'
    return r


# ===================================================================== KUNLIK STATISTIKA
@login_required
@require_permission("analytics.view")
def daily_stats(request):
    b = request.business
    if not b:
        messages.info(request, "Kunlik statistika uchun biznesni tanlang.")
        return redirect("dashboard")
    days = int(request.GET.get("days", 30)) if request.GET.get("days", "30").isdigit() else 30
    rows = daily.series(b, days)
    if not rows:
        daily.rollup_business(b, timezone.localtime(timezone.now(), tz()).date())
        rows = daily.series(b, days)
    if request.GET.get("csv") == "1":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["sana", "obunachi", "o'sish", "postlar", "stories", "ko'rish", "reach", "layk", "izoh", "ulashish", "saqlash", "story ko'rish", "havola bosish", "lid"])
        for r in rows:
            w.writerow([r.day, r.followers, r.followers_delta, r.posts, r.stories, r.views, r.reach, r.likes, r.comments, r.shares, r.saves, r.story_views, r.link_clicks, r.leads])
        resp = HttpResponse("﻿" + out.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="kunlik-{b.pk}.csv"'
        return resp
    labels = [r.day.strftime("%d.%m") for r in rows]
    charts = [{"id": "ds1", "kind": "line", "labels": labels, "series": [{"name": "Obunachi", "data": [r.followers or 0 for r in rows]}]},
              {"id": "ds2", "kind": "bar", "labels": labels, "series": [{"name": "Lid", "data": [r.leads for r in rows]}, {"name": "Havola bosish", "data": [r.link_clicks for r in rows]}]},
              {"id": "ds3", "kind": "bar", "labels": labels, "series": [{"name": "Ko'rish", "data": [r.views for r in rows]}, {"name": "Story ko'rish", "data": [r.story_views for r in rows]}]}]
    tbl = [[r.day.strftime("%d.%m.%Y"), r.followers if r.followers is not None else "—", f"{r.followers_delta:+d}" if r.followers_delta else "0", r.posts, r.stories, r.views, r.likes, r.comments, r.story_views, r.link_clicks, r.leads]
           for r in reversed(rows)]
    tot_l = sum(r.leads for r in rows)
    pills = "".join(f'<a class="pill" style="{"background:#2563eb;color:#fff" if days == d else ""}" href="?days={d}">{d} kun</a> ' for d in (7, 30, 90, 180))
    blocks = [{"type": "html", "html": f'<div class="row sb"><div>{pills}</div><a class="btn sm" href="?days={days}&csv=1">⬇ CSV</a></div>'},
              ui.kv(f"Oxirgi {days} kun", [("Obunachi (hozir)", rows[-1].followers if rows and rows[-1].followers is not None else "—"), ("O'sish", f"{sum(r.followers_delta for r in rows):+d}"),
                                          ("Lidlar", tot_l), ("Havola bosishlar", sum(r.link_clicks for r in rows)), ("Postlar", sum(r.posts for r in rows)), ("Stories", sum(r.stories for r in rows))]),
              {"type": "chart", "title": "Obunachilar (kun bo'yicha)", "id": "ds1"}, {"type": "chart", "title": "Lid va havola bosishlar", "id": "ds2"}, {"type": "chart", "title": "Ko'rishlar", "id": "ds3"},
              ui.table("Kun bo'yicha jadval (har kun saqlanib boradi)", ["Sana", "Obunachi", "O'sish", "Postlar", "Stories", "Ko'rish", "Layk", "Izoh", "Story ko'rish", "Havola", "Lid"], tbl, empty="Hali ma'lumot yo'q — birinchi kechada to'ldiriladi.")]
    return ui.page(request, "Kunlik statistika", blocks, subtitle=b.name + " · obunachi, lid va faollik har kuni saqlanadi", charts=charts)


# ===================================================================== AQLLI OGOHLANTIRISHLAR
@login_required
@require_permission("notifications.view")
def alerts_home(request):
    can_edit = request.user.is_admin or perms.businesses_for(request.user, "businesses.edit").exists()
    if request.method == "POST":
        if not can_edit:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        alerts.save_config(request.POST, user=request.user)
        audit("alerts.settings", user=request.user)
        if request.POST.get("run"):
            r = alerts.run_all()
            messages.success(request, f"Sozlama saqlandi. Tekshiruv: {r['sent']} ta yangi ogohlantirish.")
        else:
            messages.success(request, "Sozlama saqlandi.")
        return redirect("alerts_home")
    rows = ""
    from html import escape as e
    for code, label, desc, pr, _d, _fn, glob in alerts.ALERTS:
        on = alerts.is_on(code)
        p = alerts.param(code)
        inp = f'<input type="number" step="any" name="p_{code}" value="{p:g}" style="width:90px"> {e(pr[2])}' if pr else "—"
        rows += (f'<tr><td><label style="display:flex;gap:8px;align-items:center;margin:0"><input type="checkbox" name="on_{code}" {"checked" if on else ""} style="width:auto"> <b>{e(label)}</b></label>'
                 f'<div class="help">{e(desc)}{" · umumiy" if glob else ""}</div></td><td>{inp}</td></tr>')
    form = (f'<form method="post">{_csrf_input(request)}<div class="tbl"><table><tr><th>Ogohlantirish</th><th>Chegara</th></tr>{rows}</table></div>'
            f'<div class="mt row"><button class="btn primary">Saqlash</button><button class="btn" name="run" value="1">Saqlash va hozir tekshirish</button></div></form>')
    from apps.core.models import Notification
    recent = Notification.objects.filter(type="alert.smart", user=request.user).order_by("-created_at")[:25]
    blocks = [{"type": "html", "title": "Sozlamalar", "html": form if can_edit else "<p class='muted'>Faqat ko'rish (sozlash uchun menejer/admin kerak).</p>"},
              ui.table("So'nggi ogohlantirishlar", ["Vaqt", "Ogohlantirish", "Tafsilot", "Daraja"], [[ui.dt(n.created_at), ui.link(n.title, n.link) if n.link else n.title, (n.body or "")[:140], ui.badge(n.get_severity_display(), {"critical": "failed", "warn": "pending"}.get(n.severity))] for n in recent], empty="Hozircha ogohlantirish yo'q.")]
    return ui.page(request, "Aqlli ogohlantirishlar", blocks, subtitle="Tizim har 30 daqiqada tekshiradi; bir xil ogohlantirish qayta-qayta kelmaydi")
