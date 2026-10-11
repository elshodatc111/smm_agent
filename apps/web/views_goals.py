"""Maqsadlar: ro'yxat, yangi maqsad (nishon takliflari bilan), batafsil, tahrirlash, yopish."""
from __future__ import annotations

from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.connections.models import SocialAccount
from apps.core.audit import audit
from apps.goals import services as gs
from apps.goals.models import Goal

from .common import get_obj


def _account_or_404(request, pk, code):
    acc = get_object_or_404(SocialAccount, pk=pk, archived_at__isnull=True)
    if not perms.has_business(request.user, acc.business_id):
        raise Http404
    if not perms.can(request.user, code, acc.business):
        raise PermissionDenied
    return acc


@login_required
@require_permission("goals.view")
def goals_home(request):
    ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "goals.view").values_list("pk", flat=True))
    show = request.GET.get("show", "active")
    qs = Goal.objects.filter(business_id__in=ids).select_related("account", "business")
    qs = qs.filter(status="active") if show == "active" else qs.exclude(status="active")
    items = [(g, gs.compute(g)) for g in qs]
    states = [p.state for _, p in items]
    stat = {"total": len(items), "ok": sum(1 for s in states if s in ("on_track", "achieved")), "risk": sum(1 for s in states if s == "at_risk"),
            "bad": sum(1 for s in states if s == "behind")}
    groups: dict = {}
    for g, p in items:
        groups.setdefault(g.business, []).append((g, p))
    free = []
    if show == "active":
        from apps.businesses.models import Business
        for b in Business.objects.filter(pk__in=ids, archived_at__isnull=True):
            if perms.can(request.user, "goals.create", b):
                for a in gs.accounts_without_goal(b):
                    free.append(a)
    return render(request, "goals_home.html", {"title": "Maqsadlar", "groups": groups, "stat": stat, "free": free, "show": show,
                                               "can_create": any(perms.can(request.user, "goals.create", b) for b in perms.businesses_for(request.user, "goals.create")) or request.user.is_admin})


@login_required
def goal_new(request):
    acc_id = request.GET.get("account") or request.POST.get("account")
    metric = request.GET.get("metric") or request.POST.get("metric") or "followers"
    if metric not in dict(Goal.METRICS):
        metric = "followers"
    accounts = []
    for b in perms.businesses_for(request.user, "goals.create"):
        accounts += list(b.accounts.filter(archived_at__isnull=True))
    if not accounts and not request.user.is_admin:
        raise PermissionDenied
    if request.user.is_admin and not accounts:
        accounts = list(SocialAccount.objects.filter(archived_at__isnull=True))
    acc = _account_or_404(request, int(acc_id), "goals.create") if (acc_id and str(acc_id).isdigit()) else None
    ctx = {"title": "Yangi maqsad", "accounts": accounts, "acc": acc, "metric": metric, "metrics": Goal.METRICS,
           "default_end": (gs.today_local() + timedelta(days=gs.DEFAULT_DAYS)).isoformat()}
    if acc:
        sug = gs.suggest_targets(acc, metric)
        ctx.update(sug=sug, unit=gs.UNIT[metric], existing=Goal.objects.filter(account=acc, metric=metric, status="active").first())
    if request.method == "POST" and acc and request.POST.get("create"):
        try:
            raw = request.POST.get("custom") or request.POST.get("choice") or ""
            target = float(raw.replace(" ", "").replace(",", "."))
            end = date.fromisoformat(request.POST.get("end_date") or ctx["default_end"])
        except ValueError:
            messages.error(request, "Nishon va muddatni to'g'ri kiriting.")
            return render(request, "goal_new.html", ctx)
        base = gs.baseline_for(acc, metric)
        if target <= base:
            messages.error(request, f"Nishon hozirgi qiymatdan ({gs.fmt(base, metric)}) katta bo'lishi kerak.")
            return render(request, "goal_new.html", ctx)
        if end <= gs.today_local():
            messages.error(request, "Muddat kelajakda bo'lishi kerak.")
            return render(request, "goal_new.html", ctx)
        if ctx.get("existing"):
            messages.error(request, "Bu akkaunt va ko'rsatkich uchun faol maqsad bor. Uni tahrirlang yoki yoping.")
            return redirect("goal_detail", pk=ctx["existing"].pk)
        g = gs.create_goal(account=acc, metric=metric, target=target, end_date=end, note=request.POST.get("note", ""), user=request.user)
        audit("goal.create", user=request.user, business_id=g.business_id, target=str(g))
        messages.success(request, "Maqsad qo'yildi. Progress har kuni avtomatik yangilanadi.")
        return redirect("goal_detail", pk=g.pk)
    return render(request, "goal_new.html", ctx)


@login_required
def goal_detail(request, pk):
    g = get_obj(request, Goal, pk, "goals.view")
    p = gs.compute(g)
    ms = gs.milestones(g)
    ch = gs.chart_series(g)
    can_edit = perms.can(request.user, "goals.edit", g.business)
    return render(request, "goal_detail.html", {"title": str(g), "g": g, "p": p, "ms": ms, "chart": ch, "can_edit": can_edit, "unit": gs.UNIT[g.metric],
                                                "revisions": g.revisions.select_related("user")[:20]})


@login_required
@require_POST
def goal_edit(request, pk):
    g = get_obj(request, Goal, pk, "goals.edit")
    if g.status != "active":
        messages.error(request, "Yopilgan maqsadni o'zgartirib bo'lmaydi.")
        return redirect("goal_detail", pk=g.pk)
    try:
        target = float(request.POST.get("target", "").replace(" ", "").replace(",", "."))
        end = date.fromisoformat(request.POST.get("end_date", ""))
    except ValueError:
        messages.error(request, "Qiymatlarni tekshiring.")
        return redirect("goal_detail", pk=g.pk)
    if target <= g.baseline:
        messages.error(request, "Nishon boshlang'ich qiymatdan katta bo'lishi kerak.")
        return redirect("goal_detail", pk=g.pk)
    if end <= g.start_date:
        messages.error(request, "Muddat boshlanish sanasidan keyin bo'lishi kerak.")
        return redirect("goal_detail", pk=g.pk)
    gs.update_goal(g, target=target, end_date=end, note=request.POST.get("note", g.note), reason=request.POST.get("reason", ""), user=request.user)
    audit("goal.edit", user=request.user, business_id=g.business_id, target=str(g))
    messages.success(request, "Maqsad yangilandi. O'zgarish tarixga yozildi.")
    return redirect("goal_detail", pk=g.pk)


@login_required
@require_POST
def goal_close(request, pk):
    g = get_obj(request, Goal, pk, "goals.edit")
    status = request.POST.get("status")
    if status in ("achieved", "missed", "cancelled") and g.status == "active":
        gs.close_goal(g, status, request.user)
        audit("goal.close", user=request.user, business_id=g.business_id, target=f"{g} -> {status}")
        messages.success(request, "Maqsad yopildi.")
    return redirect("goal_detail", pk=g.pk)
