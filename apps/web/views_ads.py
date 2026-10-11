"""Reklama tahlili: maqsad kiritiladi → taklif (post/video, auditoriya, sinov rejasi, qo'llanma) → PDF brief."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.ads import proposals as pr
from apps.ads.brief import CONF_UZ, VERDICT_UZ, build_brief_pdf
from apps.ads.guides import guide_for
from apps.ads.models import AdProposal
from apps.businesses.passport import completeness
from apps.core.audit import audit

from .common import get_obj


@login_required
@require_permission("ads.view")
def ads_home(request):
    b = request.business
    if not b:
        ids = list(perms.businesses_for(request.user, "ads.view").values_list("pk", flat=True))
        props = AdProposal.objects.filter(business_id__in=ids).select_related("account", "business")[:24]
        return render(request, "ads_home.html", {"title": "Reklama tahlili", "b": None, "props": props, "VERDICT_UZ": VERDICT_UZ, "CONF_UZ": CONF_UZ})
    accounts = [a for a in b.accounts.filter(archived_at__isnull=True) if a.platform in pr.PLAT_AD]
    props = AdProposal.objects.filter(business=b).select_related("account")[:24]
    return render(request, "ads_home.html", {"title": "Reklama tahlili", "b": b, "accounts": accounts, "objectives": AdProposal.OBJECTIVES, "props": props,
                                             "comp": completeness(b), "can_create": perms.can(request.user, "ads.create", b), "VERDICT_UZ": VERDICT_UZ, "CONF_UZ": CONF_UZ,
                                             "default_obj": b.main_goal if b.main_goal in dict(AdProposal.OBJECTIVES) else {"followers": "subscribers", "lead": "leads", "sales": "sales", "views": "views"}.get(b.main_goal, "subscribers")})


@login_required
@require_POST
def ads_propose(request):
    b = request.business
    if not b:
        messages.info(request, "Avval yuqoridan biznesni tanlang.")
        return redirect("ads_home")
    if not perms.can(request.user, "ads.create", b):
        raise PermissionDenied
    from apps.connections.models import SocialAccount
    acc = SocialAccount.objects.filter(pk=request.POST.get("account") or 0, business=b, archived_at__isnull=True).first()
    obj = request.POST.get("objective", "")
    if not acc or obj not in dict(AdProposal.OBJECTIVES):
        messages.error(request, "Akkaunt va reklama maqsadini tanlang.")
        return redirect("ads_home")
    try:
        p = pr.create_proposal(b, acc, obj, note=request.POST.get("note", ""), user=request.user)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("ads_home")
    audit("ads.proposal", user=request.user, business_id=b.pk, target=f"{acc.platform}:{obj}")
    if p.source == "rules" and p.result.get("picks"):
        messages.info(request, "Taklif qoidalar asosida tuzildi (AI hozir javob bermadi yoki kalit kiritilmagan).")
    return redirect("ads_proposal", pk=p.pk)


@login_required
def ads_proposal(request, pk):
    p = get_obj(request, AdProposal, pk, "ads.view")
    from apps.metrics.models import Post
    posts = {x.pk: x for x in Post.objects.filter(pk__in=[k["post_id"] for k in (p.result or {}).get("picks", [])])}
    cands = {c["post_id"]: c for c in (p.evidence or {}).get("candidates", [])}
    picks = []
    for k in (p.result or {}).get("picks", []):
        picks.append({**k, "cand": cands.get(k["post_id"], {}), "post": posts.get(k["post_id"])})
    return render(request, "ad_proposal.html", {"title": f"Reklama taklifi #{p.pk}", "p": p, "r": p.result or {}, "picks": picks, "ev": p.evidence or {},
                                                "guide": guide_for(p.platform, p.objective), "VERDICT_UZ": VERDICT_UZ, "CONF_UZ": CONF_UZ,
                                                "can_edit": perms.can(request.user, "ads.edit", p.business), "plat_name": pr.PLAT_AD.get(p.platform, p.platform)})


@login_required
@require_POST
def ads_proposal_status(request, pk):
    p = get_obj(request, AdProposal, pk, "ads.edit")
    st = request.POST.get("status")
    if st in dict(AdProposal.STATUS):
        p.status = st
        p.save(update_fields=["status"])
        audit("ads.proposal.status", user=request.user, business_id=p.business_id, target=f"{p.pk}:{st}")
        messages.success(request, "Holat yangilandi.")
    return redirect("ads_proposal", pk=p.pk)


@login_required
@require_POST
def ads_proposal_redo(request, pk):
    p = get_obj(request, AdProposal, pk, "ads.create")
    n = pr.create_proposal(p.business, p.account, p.objective, note=p.note, user=request.user)
    messages.success(request, "Yangi ma'lumotlar bilan qayta hisoblandi.")
    return redirect("ads_proposal", pk=n.pk)


@login_required
def ads_proposal_pdf(request, pk):
    p = get_obj(request, AdProposal, pk, "ads.view")
    data = build_brief_pdf(p)
    audit("ads.brief.pdf", user=request.user, business_id=p.business_id, target=str(p.pk))
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="targetolog_topshiriq_{p.pk}.pdf"'
    return resp
