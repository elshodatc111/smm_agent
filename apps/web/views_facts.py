"""Faktlar va yangiliklar: takliflar lentasi, yo'nalishlar (mavzular), manbalar katalogi."""
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.core.audit import audit
from apps.facts import engine
from apps.facts.models import FactSource, FactSuggestion, FactTopic
from apps.jobs.queue import enqueue

from .common import get_obj


def _scope(request, code="facts.view"):
    if request.business:
        return [request.business.pk]
    return list(perms.businesses_for(request.user, code).values_list("pk", flat=True))


@login_required
@require_permission("facts.view")
def facts_home(request):
    ids = _scope(request)
    st = request.GET.get("status", "new")
    pl = request.GET.get("platform", "")
    kd = request.GET.get("kind", "")
    qs = FactSuggestion.objects.filter(business_id__in=ids).select_related("business", "topic")
    if st in ("new", "used", "dismissed"):
        qs = qs.filter(status=st)
    if pl in ("telegram", "instagram", "youtube"):
        qs = qs.filter(platform=pl)
    if kd in dict(FactTopic.KIND):
        qs = qs.filter(kind=kd)
    items = list(qs[:60])
    counts = {"new": FactSuggestion.objects.filter(business_id__in=ids, status="new").count(), "used": FactSuggestion.objects.filter(business_id__in=ids, status="used").count()}
    b = request.business
    return render(request, "facts_home.html", {"title": "Faktlar va yangiliklar", "items": items, "st": st, "pl": pl, "kd": kd, "counts": counts, "b": b, "kinds": FactTopic.KIND,
                                               "can_edit": bool(b and perms.can(request.user, "facts.edit", b)), "n_topics": FactTopic.objects.filter(business_id__in=ids, active=True).count(),
                                               "n_sources": FactSource.objects.filter(is_active=True).count()})


@login_required
@require_POST
def facts_refresh_now(request):
    b = request.business
    if not b:
        messages.info(request, "Yangilash uchun yuqoridan bitta biznesni tanlang.")
        return redirect("facts_home")
    if not perms.can(request.user, "facts.edit", b):
        raise PermissionDenied
    if enqueue("facts_refresh", {"business_id": b.pk}, dedupe_key=f"facts-now:{b.pk}", business_id=b.pk, queue="system"):
        messages.success(request, "Yangilash navbatga qo'yildi: bir necha daqiqadan keyin takliflar paydo bo'ladi.")
    else:
        messages.info(request, "Yangilash allaqachon ishlayapti.")
    return redirect("facts_home")


@login_required
@require_POST
def facts_suggestion_status(request, pk):
    s = get_obj(request, FactSuggestion, pk, "facts.edit")
    if request.POST.get("status") in ("new", "used", "dismissed"):
        s.status = request.POST["status"]
        s.save(update_fields=["status"])
    return redirect(request.POST.get("next") or "facts_home")


class TopicForm(forms.ModelForm):
    keywords_text = forms.CharField(label="Kalit so'zlar (inglizcha, vergul bilan)", required=False,
                                    help_text="Dunyo manbalarida qidirish uchun. Masalan: graphic design trends, logo design, branding")
    kinds = forms.MultipleChoiceField(label="Qanday kontent kerak", choices=FactTopic.KIND, widget=forms.CheckboxSelectMultiple, initial=["fact", "news", "tip"])

    class Meta:
        model = FactTopic
        fields = ["platform", "title"]
        labels = {"platform": "Ijtimoiy tarmoq", "title": "Yo'nalish nomi (o'zbekcha)"}


@login_required
@require_permission("facts.view")
def facts_topics(request):
    b = request.business
    if not b:
        messages.info(request, "Yo'nalishlar uchun yuqoridan bitta biznesni tanlang.")
        return redirect("facts_home")
    can = perms.can(request.user, "facts.create", b)
    form = TopicForm(request.POST or None)
    form.fields["platform"].choices = [(k, v) for k, v in FactTopic.PLATFORMS if k != "youtube"]
    if request.method == "POST":
        if not can:
            raise PermissionDenied
        if form.is_valid():
            t = form.save(commit=False)
            t.business = b
            t.keywords = [x.strip() for x in form.cleaned_data["keywords_text"].split(",") if x.strip()]
            t.kinds = form.cleaned_data["kinds"]
            t.save()
            audit("facts.topic", user=request.user, business_id=b.pk, target=t.title)
            messages.success(request, "Yo'nalish qo'shildi.")
            return redirect("facts_topics")
    default_kw = ", ".join(b.template.topics) if b.template and b.template.topics else ""
    return render(request, "facts_topics.html", {"title": "Yo'nalishlar", "b": b, "topics": b.fact_topics.all(), "form": form, "can": can, "default_kw": default_kw})


@login_required
@require_POST
def facts_topic_action(request, pk, action):
    t = get_obj(request, FactTopic, pk, "facts.edit")
    if action == "toggle":
        t.active = not t.active
        t.save(update_fields=["active"])
    elif action == "delete" and perms.can(request.user, "facts.delete", t.business):
        t.delete()
        messages.success(request, "Yo'nalish o'chirildi.")
    return redirect("facts_topics")


class SourceForm(forms.Form):
    name = forms.CharField(label="Manba nomi", max_length=120)
    url = forms.URLField(label="Sayt manzili", assume_scheme="https")
    feed_url = forms.URLField(label="RSS / Atom manzili", assume_scheme="https", help_text="Saytning RSS (yangiliklar lentasi) manzili.")
    language = forms.CharField(label="Til (kod)", max_length=5, initial="en")
    domains = forms.CharField(label="Sohalar (vergul bilan)", required=False, help_text="Masalan: design, smm, tech, business, education, food, health. Bo'sh qoldirsangiz barcha bizneslarga mos.")


@login_required
@require_permission("facts.view")
def facts_sources(request):
    engine.ensure_sources()
    can = perms.can(request.user, "facts.edit", request.business) if request.business else request.user.is_admin
    form = SourceForm(request.POST or None)
    if request.method == "POST":
        if not can:
            raise PermissionDenied
        if form.is_valid():
            d = form.cleaned_data
            if FactSource.objects.filter(feed_url=d["feed_url"]).exists():
                messages.error(request, "Bu RSS manzil allaqachon qo'shilgan.")
            else:
                FactSource.objects.create(name=d["name"], url=d["url"], feed_url=d["feed_url"], tier="C", language=d["language"], is_system=False,
                                          domains=[x.strip().lower() for x in d["domains"].split(",") if x.strip()])
                audit("facts.source", user=request.user, target=d["name"])
                messages.success(request, "Manba qo'shildi. «Tekshirish» tugmasi bilan ishlashini sinab ko'ring.")
            return redirect("facts_sources")
    return render(request, "facts_sources.html", {"title": "Manbalar katalogi", "sources": FactSource.objects.all(), "off": FactSource.objects.filter(is_active=False), "form": form, "can": can})


@login_required
@require_POST
def facts_source_action(request, pk, action):
    if not (perms.can(request.user, "facts.edit", request.business) if request.business else request.user.is_admin):
        raise PermissionDenied
    s = get_object_or_404(FactSource, pk=pk)
    if action == "toggle":
        s.is_active = not s.is_active
        s.save(update_fields=["is_active"])
        messages.success(request, f"«{s.name}» " + ("qayta yoqildi." if s.is_active else "ro'yxatdan olib tashlandi (pastdagi «O'chirilganlar» bo'limida turadi)."))
    elif action == "test":
        r = engine.refresh_source(s)
        messages.success(request, f"«{s.name}» ishlayapti: {r['new']} ta yangi material.") if r["ok"] else messages.error(request, f"«{s.name}» ishlamadi: {r['error']}")
    elif action == "delete":
        if s.is_system:   # tizim manbasi qayta tiklanib qolmasin: faqat o'chiriladi
            s.is_active = False
            s.save(update_fields=["is_active"])
        else:
            s.delete()
        messages.success(request, "Manba o'chirildi.")
    return redirect("facts_sources")
