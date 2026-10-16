"""Sozlamalar → Biznes turlari va Biznes pasporti."""
from __future__ import annotations

import re

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.businesses import passport as pp
from apps.businesses.models import Business, BusinessTemplate
from apps.core.audit import audit

KINDS = {"text": "Qisqa matn", "long": "Uzun matn", "choice": "Tanlov", "number": "Raqam"}
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def parse_fields(text: str) -> tuple[list[dict], list[str]]:
    """Qatorlar: kalit | Savol | tur | variantlar (; bilan) | izoh"""
    out, errs, seen = [], [], set()
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            errs.append(f"{n}-qator: kamida «kalit | Savol» kerak.")
            continue
        key, label = parts[0].lower(), parts[1]
        kind = (parts[2].lower() if len(parts) > 2 and parts[2] else "text")
        if not KEY_RE.match(key):
            errs.append(f"{n}-qator: kalit faqat lotin harf, raqam va _ bo'lishi kerak (masalan: narx_royxati).")
            continue
        if key in seen:
            errs.append(f"{n}-qator: «{key}» kaliti takrorlangan.")
            continue
        if kind not in KINDS:
            errs.append(f"{n}-qator: tur {', '.join(KINDS)} dan biri bo'lishi kerak.")
            continue
        f = {"key": key, "label": label, "kind": kind, "help": parts[4] if len(parts) > 4 else ""}
        if kind == "choice":
            ch = [c.strip() for c in (parts[3] if len(parts) > 3 else "").split(";") if c.strip()]
            if len(ch) < 2:
                errs.append(f"{n}-qator: «tanlov» uchun kamida 2 variant kerak (; bilan ajrating).")
                continue
            f["choices"] = ch
        seen.add(key)
        out.append(f)
    return out, errs


def fields_to_text(fields: list[dict]) -> str:
    rows = []
    for f in fields or []:
        rows.append(" | ".join([f["key"], f["label"], f.get("kind", "text"), ";".join(f.get("choices") or []), f.get("help", "")]).rstrip(" |"))
    return "\n".join(rows)


class TypeForm(forms.Form):
    name = forms.CharField(label="Biznes turi nomi", max_length=120, help_text="Masalan: Gul do'koni, Avtomaktab, Tikuvchilik sexi")
    key = forms.SlugField(label="Kalit (lotin)", max_length=50, help_text="Faqat lotin harf, raqam va _ . Keyin o'zgartirib bo'lmaydi.")
    description = forms.CharField(label="Qisqa izoh", required=False, max_length=300)
    fields_text = forms.CharField(label="Pasport savollari", required=False, widget=forms.Textarea(attrs={"rows": 10}),
                                  help_text="Har qatorda bitta savol: <code>kalit | Savol | tur | variantlar | izoh</code>. Tur: text, long, choice, number. "
                                            "«choice» uchun variantlarni ; bilan ajrating. Masalan:<br><code>gul_turlari | Qaysi gullar sotiladi | long</code><br><code>yetkazish | Yetkazib berish | choice | Bor;Yo'q;Pulli</code>")
    advice = forms.CharField(label="Maslahat (SMM bo'yicha qisqa yo'l-yo'riq)", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    content_types = forms.CharField(label="Tavsiya etilgan kontent turlari (vergul bilan)", required=False)

    def __init__(self, *a, instance=None, **kw):
        super().__init__(*a, **kw)
        self.instance = instance
        if instance:
            self.fields["key"].disabled = True

    def clean_key(self):
        k = self.cleaned_data["key"].lower()
        if not self.instance and BusinessTemplate.objects.filter(key=k).exists():
            raise forms.ValidationError("Bu kalit band.")
        return k

    def clean_fields_text(self):
        fields, errs = parse_fields(self.cleaned_data.get("fields_text", ""))
        if errs:
            raise forms.ValidationError(errs)
        self.parsed_fields = fields
        return self.cleaned_data.get("fields_text", "")


@login_required
@require_permission("settings.view")
def biztype_list(request):
    can = perms.can(request.user, "settings.configure", None)
    rows = []
    for t in BusinessTemplate.objects.all():
        rows.append({"t": t, "n_fields": len(t.profile_fields or []), "n_biz": t.business_set.count()})
    return render(request, "biztypes.html", {"title": "Biznes turlari", "rows": rows, "can": can})


@login_required
@require_permission("settings.configure")
def biztype_edit(request, pk=None):
    inst = get_object_or_404(BusinessTemplate, pk=pk) if pk else None
    initial = {}
    if inst:
        c = inst.config or {}
        initial = {"name": inst.name, "key": inst.key, "description": inst.description,
                   "fields_text": fields_to_text(inst.profile_fields), "advice": c.get("advice", ""), "content_types": ", ".join(c.get("content_types") or [])}
    form = TypeForm(request.POST or None, initial=initial, instance=inst)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        cfg = dict((inst.config if inst else {}) or {})
        cfg["advice"] = d["advice"]
        cfg["content_types"] = [x.strip() for x in d["content_types"].split(",") if x.strip()]
        cfg.setdefault("defaults", {"ctr": 0.012, "click_to_lead": 0.05, "cpm": 22000})
        vals = dict(name=d["name"], description=d["description"],
                    profile_fields=form.parsed_fields, config=cfg)
        if inst:
            for k, v in vals.items():
                setattr(inst, k, v)
            inst.save()
        else:
            inst = BusinessTemplate.objects.create(key=d["key"], is_system=False, sort=60, **vals)
        audit("biztype.save", user=request.user, target=inst.key)
        messages.success(request, "Biznes turi saqlandi.")
        return redirect("biztype_list")
    return render(request, "biztype_form.html", {"title": "Yangi biznes turi" if not inst else f"Tahrirlash: {inst.name}", "form": form, "inst": inst})


@login_required
@require_POST
@require_permission("settings.configure")
def biztype_delete(request, pk):
    t = get_object_or_404(BusinessTemplate, pk=pk)
    if t.is_system:
        messages.error(request, "Tizim turini o'chirib bo'lmaydi (faqat tahrirlash mumkin).")
    elif t.business_set.exists():
        messages.error(request, "Bu turdagi bizneslar bor. Avval ularning turini o'zgartiring.")
    else:
        audit("biztype.delete", user=request.user, target=t.key)
        t.delete()
        messages.success(request, "Biznes turi o'chirildi.")
    return redirect("biztype_list")


def _biz(request, pk, code):
    b = get_object_or_404(Business, pk=pk)
    if not perms.has_business(request.user, b.pk):
        raise Http404
    if not perms.can(request.user, code, b):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    return b


def _clean_choice(v, f):
    v = (v or "").strip()
    if f.get("kind") == "choice" and v and v not in (f.get("choices") or []):
        return ""
    return v[:2000]


@login_required
def passport(request, pk):
    b = _biz(request, pk, "businesses.view")
    can_edit = perms.can(request.user, "businesses.edit", b)
    if request.method == "POST":
        if not can_edit:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        data = {"core": {}, "type": {}, "general": {}}
        if request.POST.get("template"):
            t = BusinessTemplate.objects.filter(pk=request.POST["template"]).first()
            if t and (not b.template or b.template_id != t.pk):
                b.template = t
        for s in pp.sections(b):
            for f in s["fields"]:
                data[f["section"]][f["key"]] = _clean_choice(request.POST.get(f"{f['section']}__{f['key']}"), f)
        pp.save_answers(b, data)
        Business.objects.filter(pk=b.pk).update(brand_update_suggested=True)
        audit("business.passport", user=request.user, business_id=b.pk)
        messages.success(request, "Biznes pasporti saqlandi.")
        return redirect("passport", pk=b.pk)
    secs = pp.sections(b)
    return render(request, "passport.html", {"title": f"Biznes pasporti: {b.name}", "b": b, "secs": secs, "comp": pp.completeness(b),
                                             "can_edit": can_edit, "types": BusinessTemplate.objects.all()})
