from __future__ import annotations

import json
import re
from pathlib import Path

import markdown
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.auth import LockedOut, login_check
from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.core.models import AuditLog, Notification, NotificationPref
from apps.core.notify import TYPES
from apps.metrics import analytics as an

from . import dash, spa


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    err = ""
    if request.method == "POST":
        try:
            u = login_check(request, request.POST.get("username", "").strip(), request.POST.get("password", ""))
        except LockedOut as e:
            u, err = None, str(e)
        if u and u.is_active:
            login(request, u)
            nxt = request.POST.get("next") or "/"
            return redirect(nxt if url_has_allowed_host_and_scheme(nxt, {request.get_host()}) else "/")
        err = err or "Login yoki parol noto'g'ri."
    return spa.respond(request, {"kind": "login", "error": err, "next": request.GET.get("next", ""), "brand": spa.brand_payload()}, 401 if err else 200)


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
@require_POST
def theme_view(request):
    t = request.POST.get("theme")
    if t in ("light", "dark"):
        request.user.theme = t
        request.user.save(update_fields=["theme"])
    return HttpResponse(status=204)


@login_required
@require_POST
def business_select(request):
    bid = request.POST.get("business")
    if bid and bid.isdigit() and perms.has_business(request.user, int(bid)):
        request.session["business_id"] = int(bid)
    else:
        request.session.pop("business_id", None)
    return HttpResponse(status=204)


def _biz_summary(b):
    c = an.compare_periods(b, 30)
    accs = list(b.accounts.filter(archived_at__isnull=True))
    bad = [a for a in accs if a.status in ("error", "token_expiring")]
    from apps.content.models import ContentTarget
    sched = ContentTarget.objects.filter(account__business=b, status="pending", item__status__in=["scheduled", "approved"], item__deleted_at__isnull=True,
                                         item__scheduled_at__gte=timezone.now()).count()
    return {"id": b.pk, "name": b.name, "kpi": dash.kpi_json(c["current"], c["delta_pct"]), "accounts": len(accs), "scheduled": sched,
            "problems": [{"id": a.pk, "name": a.name, "status": a.get_status_display()} for a in bad]}


@login_required
@require_permission("dashboard.view")
def dashboard(request):
    b = request.business
    if b is None:
        rows = [_biz_summary(x) for x in perms.businesses_for(request.user, "dashboard.view")]
        return spa.respond(request, {"kind": "dashboard_all", "rows": rows})
    from apps.content.models import ContentItem
    from apps.jobs.models import Job
    c = an.compare_periods(b, 30)
    types = an.by_type(b)
    accounts = [dash.account_row(b, a) for a in b.accounts.filter(archived_at__isnull=True)]
    upcoming = ContentItem.objects.filter(business=b, scheduled_at__gte=timezone.now(), status__in=["scheduled", "draft", "approved"]).order_by("scheduled_at")[:6]
    freq = an.post_frequency(b)
    return spa.respond(request, {
        "kind": "dashboard", "business": {"id": b.pk, "name": b.name}, "kpi": dash.kpi_json(c["current"], c["delta_pct"]),
        "per_week": round(freq.get("per_week") or 0, 1) if isinstance(freq, dict) else 0,
        "series": an.business_follower_series(b, 30), "types": [{"type": t["type"], "count": t["count"], "er": round((t["avg_er"] or 0) * 100, 2)} for t in types],
        "top": [dash.post_json(r) for r in an.top_posts(b, 5)], "worst": [dash.post_json(r) for r in an.top_posts(b, 3, worst=True)],
        "upcoming": [{"id": i.pk, "title": i.title, "at": i.scheduled_at.isoformat(), "status": i.get_status_display(), "type": i.media_type} for i in upcoming],
        "accounts": accounts,
        "imports": [{"id": j.pk, "progress": j.progress, "status": j.get_status_display()} for j in
                    Job.objects.filter(business_id=b.pk, type="historical_import", status__in=["pending", "running"])]})


@login_required
@require_permission("notifications.view")
def notification_list(request):
    qs = Notification.objects.filter(user=request.user)
    if request.method == "POST":
        qs.filter(read_at__isnull=True).update(read_at=timezone.now())
        return redirect("notification_list")
    page = Paginator(qs, 30).get_page(request.GET.get("p"))
    prefs = {p.type: p for p in NotificationPref.objects.filter(user=request.user)}
    return spa.respond(request, {
        "kind": "notifications", "pager": spa.pager_json(page),
        "items": [{"id": n.pk, "title": n.title, "body": n.body[:240], "link": n.link, "severity": n.severity, "read": bool(n.read_at),
                   "at": n.created_at.isoformat()} for n in page],
        "types": [{"key": k, "label": v, "web": prefs[k].web if k in prefs else True, "telegram": prefs[k].telegram if k in prefs else False}
                  for k, v in TYPES.items()]})


@login_required
@require_POST
def notification_prefs(request):
    for t in TYPES:
        NotificationPref.objects.update_or_create(user=request.user, type=t, defaults={
            "web": request.POST.get(f"web_{t}") == "on", "telegram": request.POST.get(f"tg_{t}") == "on"})
    messages.success(request, "Bildirishnoma sozlamalari saqlandi.")
    return redirect("notification_list")


@login_required
@require_permission("users.view")
def audit_list(request):
    qs = AuditLog.objects.select_related("user").order_by("-at")
    if not request.user.is_admin:
        raise Http404
    q = request.GET.get("q")
    if q:
        qs = qs.filter(action__icontains=q)
    page = Paginator(qs, 50).get_page(request.GET.get("p"))
    return spa.respond(request, {"kind": "audit", "q": q or "", "pager": spa.pager_json(page), "rows": [
        {"at": a.at.isoformat(), "user": str(a.user) if a.user else "—", "action": a.action, "target": a.target, "detail": json.dumps(a.detail, ensure_ascii=False)[:200] if a.detail else ""}
        for a in page]})


GUIDE_DIR = Path(settings.BASE_DIR) / "docs" / "setup"


def _guides():
    out = []
    for f in sorted(GUIDE_DIR.glob("*.md")):
        first = f.read_text(encoding="utf-8").split("\n", 1)[0].lstrip("# ").strip()
        out.append({"slug": f.stem, "title": first or f.stem})
    return out


@login_required
@require_permission("guides.view")
def guide_index(request):
    return spa.respond(request, {"kind": "guide", "guides": _guides(), "slug": "", "html": ""})


@login_required
@require_permission("guides.view")
def guide_view(request, slug):
    if not re.fullmatch(r"[\w\-]+", slug):
        raise Http404
    f = GUIDE_DIR / f"{slug}.md"
    if not f.exists():
        raise Http404
    html = markdown.markdown(f.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "toc", "sane_lists"])
    return spa.respond(request, {"kind": "guide", "guides": _guides(), "slug": slug, "html": html})
