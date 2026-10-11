from __future__ import annotations

from django.shortcuts import render

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.businesses import services as bsvc
from apps.businesses.models import BrandProfile, Business, BusinessTemplate
from apps.core.audit import audit
from . import ui
from .forms import BrandForm, BusinessForm


@login_required
@require_permission("businesses.view")
def business_list(request):
    qs = perms.businesses_for(request.user, "businesses.view")
    rows = [[ui.link(b.name, f"/bizneslar/{b.pk}/"), b.industry or "—", b.region or "—", b.accounts.filter(archived_at__isnull=True).count(),
             ui.badge("Faol" if b.autopublish_enabled else "Avto-nashr o'chiq", "active" if b.autopublish_enabled else "paused")] for b in qs]
    tb = [{"label": "Yangi biznes", "url": "/bizneslar/yangi/", "cls": "primary"}] if perms.can(request.user, "businesses.create", None) or request.user.is_admin else []
    return ui.page(request, "Bizneslar", [ui.table(None, ["Nomi", "Soha", "Hudud", "Ulanishlar", "Holat"], rows)], toolbar=tb)


@login_required
@require_permission("businesses.create")
def business_new(request):
    from apps.businesses.models import Business
    from apps.core.settings_store import get_setting
    limit = int(get_setting("agency.max_businesses", 10) or 0)
    if limit and Business.objects.filter(archived_at__isnull=True).count() >= limit:
        messages.error(request, f"Bizneslar chegarasi: {limit} ta. Yangisini qo'shish uchun biror biznesni arxivlang yoki Sozlamalar → Umumiy bo'limida chegarani oshiring.")
        return redirect("business_list")
    form = BusinessForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        b = form.save()
        if not b.template_id:
            b.template = BusinessTemplate.objects.filter(key="boshqa").first()
            b.save(update_fields=["template"])
        from apps.accounts.models import UserBusinessAccess
        if not request.user.is_admin:
            UserBusinessAccess.objects.get_or_create(user=request.user, business=b, defaults={"all_flag": False})
        from apps.accounts.services import bump_permissions
        bump_permissions()
        audit("business.create", user=request.user, business_id=b.pk, target=b.name)
        messages.success(request, "Biznes yaratildi. Endi biznes pasportini to'ldiring: tavsiyalar shunga tayanadi.")
        return redirect("passport", pk=b.pk)
    return render(request, "form.html", {"title": "Yangi biznes", "form": form, "back": "/bizneslar/"})


@login_required
def business_edit(request, pk):
    b = _biz_or_404(request, pk, "businesses.edit")
    old = {f: getattr(b, f) for f in bsvc.BUSINESS_PROMPT_FIELDS}
    form = BusinessForm(request.POST or None, request.FILES or None, instance=b)
    if request.method == "POST" and form.is_valid():
        form.save()
        bsvc.business_changed(b, old)
        audit("business.edit", user=request.user, business_id=b.pk)
        messages.success(request, "Saqlandi.")
        return redirect("business_detail", pk=b.pk)
    return render(request, "form.html", {"title": f"Tahrirlash: {b.name}", "form": form, "back": f"/bizneslar/{b.pk}/"})


def _biz_or_404(request, pk, code):
    from django.http import Http404
    b = get_object_or_404(Business, pk=pk)
    if not perms.has_business(request.user, b.pk):
        raise Http404
    if not perms.can(request.user, code, b):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    return b


@login_required
def business_detail(request, pk):
    b = _biz_or_404(request, pk, "businesses.view")
    from apps.businesses.passport import completeness
    from apps.goals import services as gs
    act = b.active_brand
    can_edit = perms.can(request.user, "businesses.edit", b)
    goals = gs.summary_for(b, 6) if perms.can(request.user, "goals.view", b) else []
    form = BrandForm(initial={"content": (act.content if act else "")})
    return render(request, "business_detail.html", {
        "title": b.name, "b": b, "comp": completeness(b), "versions": b.brand_profiles.order_by("-version"), "act": act, "can_edit": can_edit,
        "accounts": b.accounts.filter(archived_at__isnull=True), "goals": goals, "goal_free": gs.accounts_without_goal(b) if perms.can(request.user, "goals.create", b) else [],
        "brand_form": form, "can_ai": perms.can(request.user, "ai_studio.create", b), "can_pub": perms.can(request.user, "publish.publish", b)})


@login_required
@require_POST
def brand_new(request, pk):
    b = _biz_or_404(request, pk, "businesses.edit")
    form = BrandForm(request.POST)
    if form.is_valid():
        bsvc.save_brand_version(b, form.cleaned_data["content"], user=request.user, note=form.cleaned_data["note"])
        messages.success(request, "Yangi versiya qoralama sifatida saqlandi.")
    return redirect("business_detail", pk=b.pk)


@login_required
@require_POST
def brand_ai(request, pk):
    b = _biz_or_404(request, pk, "ai_studio.create")
    from apps.studio.services import generate_brand_profile
    try:
        generate_brand_profile(b, request.user)
        messages.success(request, "AI brend xotirasi qoralamasini yaratdi. Ko'rib chiqib tasdiqlang.")
    except Exception as e:  # noqa: BLE001
        messages.error(request, getattr(e, "user_message_uz", None) or f"AI xatosi: {e}")
    return redirect("business_detail", pk=b.pk)


@login_required
@require_POST
def brand_approve(request, pk, vid):
    b = _biz_or_404(request, pk, "businesses.edit")
    bsvc.approve_brand(get_object_or_404(BrandProfile, pk=vid, business=b), request.user)
    messages.success(request, "Brend xotirasi tasdiqlandi.")
    return redirect("business_detail", pk=b.pk)


@login_required
@require_POST
def brand_restore(request, pk, vid):
    b = _biz_or_404(request, pk, "businesses.edit")
    bsvc.restore_brand(get_object_or_404(BrandProfile, pk=vid, business=b), request.user)
    messages.success(request, "Eski versiya yangi versiya sifatida tiklandi.")
    return redirect("business_detail", pk=b.pk)


@login_required
@require_POST
def business_killswitch(request, pk):
    b = _biz_or_404(request, pk, "publish.publish")
    b.autopublish_enabled = not b.autopublish_enabled
    b.save(update_fields=["autopublish_enabled"])
    audit("business.killswitch", user=request.user, business_id=b.pk, detail={"enabled": b.autopublish_enabled})
    messages.warning(request, "Avto-nashr " + ("yoqildi." if b.autopublish_enabled else "O'CHIRILDI: hech narsa avtomatik chiqmaydi."))
    return redirect("business_detail", pk=b.pk)
