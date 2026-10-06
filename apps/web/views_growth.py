"""O'sish bo'limlari: G'oyalar banki, Kunlik statistika, Aqlli ogohlantirishlar."""
from __future__ import annotations

import csv
import io

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
from apps.core.utils import tz
from apps.metrics import daily
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
    tabs = ui.tabs([(v, f"?s={k}", st == k) for k, v in (("", "Faol"), ("new", "Yangi"), ("saved", "Saqlangan"), ("used", "Ishlatilgan"), ("rejected", "Rad etilgan"))])
    rows = []
    for i in qs[:80]:
        rows.append([ui.dt(i.day) if False else i.day.strftime("%d.%m.%Y"), ui.link(i.title, f"/goyalar/{i.pk}/", (i.hook or "")[:90]), i.business.name, (i.platform or "—").title(),
                     idea_svc.FMT_UZ.get(i.fmt, i.fmt or "—"), SRC_UZ.get(i.source, i.source), ui.badge(i.get_status_display(), {"new": "pending", "saved": "approved", "used": "ok", "rejected": "failed"}.get(i.status))])
    tb = []
    if request.business and perms.can(request.user, "ai_studio.create", request.business):
        tb = [{"label": "✨ Hozir yangi g'oya", "post": "/goyalar/yaratish/", "cls": "primary"}]
    blocks = [tabs, ui.table(None, ["Sana", "G'oya", "Biznes", "Platforma", "Format", "Manba", "Holat"], rows, empty="Hali g'oya yo'q. Har kuni ertalab tahlildan avtomatik qo'shiladi; «Hozir yangi g'oya» tugmasi bilan ham olasiz.")]
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


def _csrf_input(request) -> str:
    from django.middleware.csrf import get_token
    return f'<input type="hidden" name="csrfmiddlewaretoken" value="{get_token(request)}">'


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
        w.writerow(["sana", "obunachi", "o'sish", "postlar", "stories", "ko'rish", "reach", "layk", "izoh", "ulashish", "saqlash", "story ko'rish", "havola bosish"])
        for r in rows:
            w.writerow([r.day, r.followers, r.followers_delta, r.posts, r.stories, r.views, r.reach, r.likes, r.comments, r.shares, r.saves, r.story_views, r.link_clicks])
        resp = HttpResponse("﻿" + out.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="kunlik-{b.pk}.csv"'
        return resp
    labels = [r.day.strftime("%d.%m") for r in rows]
    charts = [{"id": "ds1", "kind": "line", "labels": labels, "series": [{"name": "Obunachi", "data": [r.followers or 0 for r in rows]}]},
              {"id": "ds2", "kind": "bar", "labels": labels, "series": [{"name": "Havola bosish", "data": [r.link_clicks for r in rows]}]},
              {"id": "ds3", "kind": "bar", "labels": labels, "series": [{"name": "Ko'rish", "data": [r.views for r in rows]}, {"name": "Story ko'rish", "data": [r.story_views for r in rows]}]}]
    tbl = [[r.day.strftime("%d.%m.%Y"), r.followers if r.followers is not None else "—", f"{r.followers_delta:+d}" if r.followers_delta else "0", r.posts, r.stories, r.views, r.likes, r.comments, r.story_views, r.link_clicks]
           for r in reversed(rows)]
    blocks = [ui.tabs([(f"{d} kun", f"?days={d}", days == d) for d in (7, 30, 90, 180)]),
              {"type": "actions", "title": None, "buttons": [{"label": "⬇ CSV yuklab olish", "href": f"/kunlik/?days={days}&csv=1", "cls": ""}]},
              ui.kv(f"Oxirgi {days} kun", [("Obunachi (hozir)", rows[-1].followers if rows and rows[-1].followers is not None else "—"), ("O'sish", f"{sum(r.followers_delta for r in rows):+d}"),
                                          ("Havola bosishlar", sum(r.link_clicks for r in rows)), ("Postlar", sum(r.posts for r in rows)), ("Stories", sum(r.stories for r in rows))]),
              {"type": "chart", "title": "Obunachilar (kun bo'yicha)", "id": "ds1"}, {"type": "chart", "title": "Havola bosishlar", "id": "ds2"}, {"type": "chart", "title": "Ko'rishlar", "id": "ds3"},
              ui.table("Kun bo'yicha jadval (har kun saqlanib boradi)", ["Sana", "Obunachi", "O'sish", "Postlar", "Stories", "Ko'rish", "Layk", "Izoh", "Story ko'rish", "Havola"], tbl, empty="Hali ma'lumot yo'q — birinchi kechada to'ldiriladi.")]
    return ui.page(request, "Kunlik statistika", blocks, subtitle=b.name + " · obunachi va faollik har kuni saqlanadi", charts=charts)


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
