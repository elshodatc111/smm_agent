from __future__ import annotations

import re
from pathlib import Path

import markdown
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.auth import LockedOut, login_check
from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.core.models import AuditLog, Notification, NotificationPref
from apps.core.notify import TYPES
from apps.metrics import analytics as an


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
    return render(request, "auth/login.html", {"error": err, "next": request.GET.get("next", "")})


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
    return redirect(request.META.get("HTTP_REFERER") or "dashboard")


def _biz_summary(b, user):
    c = an.compare_periods(b, 30)
    accs = list(b.accounts.filter(archived_at__isnull=True))
    bad = [a for a in accs if a.status in ("error", "token_expiring")]
    return {"b": b, "kpi": c["current"], "delta": c["delta_pct"], "accounts": len(accs), "problems": bad}


@login_required
@require_permission("dashboard.view")
def dashboard(request):
    b = request.business
    ctx = {}
    if b is None:
        rows = [_biz_summary(x, request.user) for x in perms.businesses_for(request.user, "dashboard.view")]
        ctx["rows"] = rows
        return render(request, "dashboard_all.html", ctx)
    c = an.compare_periods(b, 30)
    series = an.business_follower_series(b, 30)
    from apps.content.models import ContentItem
    from apps.jobs.models import Job
    ctx.update(b=b, kpi=c["current"], delta=c["delta_pct"], series=series,
               top=an.top_posts(b, 5), worst=an.top_posts(b, 3, worst=True), types=an.by_type(b),
               upcoming=ContentItem.objects.filter(business=b, scheduled_at__gte=timezone.now(), status__in=["scheduled", "draft"]).order_by("scheduled_at")[:6],
               accounts=b.accounts.filter(archived_at__isnull=True),
               imports=Job.objects.filter(business_id=b.pk, type="historical_import", status__in=["pending", "running"]),
               freq=an.post_frequency(b))
    return render(request, "dashboard.html", ctx)


@login_required
@require_permission("notifications.view")
def notification_list(request):
    qs = Notification.objects.filter(user=request.user)
    if request.method == "POST":
        qs.filter(read_at__isnull=True).update(read_at=timezone.now())
        return redirect("notification_list")
    page = Paginator(qs, 30).get_page(request.GET.get("p"))
    prefs = {p.type: p for p in NotificationPref.objects.filter(user=request.user)}
    return render(request, "notifications.html", {"page": page, "types": TYPES, "prefs": prefs})


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
    return render(request, "audit.html", {"page": Paginator(qs, 50).get_page(request.GET.get("p")), "q": q or ""})


GUIDE_DIR = Path(settings.BASE_DIR) / "docs" / "setup"
GUIDE_TITLES = {}


def _guides():
    out = []
    for f in sorted(GUIDE_DIR.glob("*.md")):
        first = f.read_text(encoding="utf-8").split("\n", 1)[0].lstrip("# ").strip()
        out.append({"slug": f.stem, "title": first or f.stem})
    return out


@login_required
@require_permission("guides.view")
def guide_index(request):
    return render(request, "guides_index.html", {"guides": _guides()})


@login_required
@require_permission("guides.view")
def guide_view(request, slug):
    if not re.fullmatch(r"[\w\-]+", slug):
        raise Http404
    f = GUIDE_DIR / f"{slug}.md"
    if not f.exists():
        raise Http404
    html = markdown.markdown(f.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "toc", "sane_lists"])
    return render(request, "guide.html", {"html": html, "guides": _guides(), "slug": slug})
