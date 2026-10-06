"""Tizim holati, sozlamalar, foydalanuvchilar/rollar, mijoz boti taklifnomalari."""
from __future__ import annotations

import json
import re

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.models import Role, User, UserBusinessAccess
from apps.accounts.permissions_registry import ACTIONS, MODULES
from apps.accounts.services import bump_permissions, delete_role, guard_admin_change, perms, set_role_permissions
from apps.ai_router.models import AIKey
from apps.businesses.models import Business
from apps.core import settings_store as ss
from apps.core.audit import audit
from apps.health import services as hs
from apps.jobs.models import Job
from apps.jobs.queue import enqueue
from apps.tgbot.bot import create_invite
from apps.tgbot.models import ClientBotUser, ClientInvite
from . import spa, ui

# ---------------- Tizim holati ----------------


@login_required
@require_permission("system_health.view")
def health(request):
    snap = hs.snapshot()
    for c in snap.get("connections", []):
        if c.get("expires") and hasattr(c["expires"], "strftime"):
            c["expires"] = c["expires"].strftime("%d.%m.%Y")
    return spa.respond(request, {"kind": "health", "s": snap})


@login_required
@require_permission("system_health.view")
def job_list(request):
    qs = Job.objects.order_by("-created_at")
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    page = Paginator(qs, 50).get_page(request.GET.get("p"))
    rows = [[j.pk, j.type, j.queue, ui.badge(j.status, j.status), j.attempts, ui.dt(j.created_at), (j.last_error or "")[:100] or "—",
             ui.btn("Qayta", f"/tizim/vazifalar/{j.pk}/qayta/") if j.status in ("failed", "dead") else ""] for j in page]
    cur = request.GET.get("status", "")
    chips = ui.tabs([("Hammasi", "?", not cur)] + [(s, f"?status={s}", cur == s) for s in ("pending", "running", "done", "failed")])
    return ui.page(request, "Vazifalar navbati", [chips, ui.table(None, ["ID", "Tur", "Navbat", "Holat", "Urinish", "Yaratilgan", "Xato", ""], rows)])


@login_required
@require_POST
@require_permission("system_health.configure")
def job_retry(request, pk):
    j = get_object_or_404(Job, pk=pk)
    j.status, j.attempts, j.last_error = "pending", 0, ""
    j.save(update_fields=["status", "attempts", "last_error"])
    return redirect("job_list")


@login_required
@require_POST
@require_permission("system_health.configure")
def backup_now(request):
    j = enqueue("backup_db", {}, queue="system", dedupe_key="backup:manual")
    messages.success(request, "Zaxira nusxa navbatga qo'yildi." if j else "Zaxira allaqachon navbatda.")
    return redirect("health")


# ---------------- Sozlamalar ----------------
# (key, label, kind, help) ; kind: text|secret|int|bool|list|json|choice:<a,b>
TABS = {
    "umumiy": ("Umumiy", [("general.system_name", "Tizim nomi", "text", ""), ("general.brand_color", "Brend rangi", "text", "#E11D2E"), ("general.public_url", "Tashqi manzil (ixtiyoriy)", "text", "Masalan https://smm.domen.uz — mijozga hisobot havolasi va telefon ilovasi uchun (Cloudflare Tunnel)"), ("agency.max_businesses", "Bizneslar soni chegarasi", "int", "Agentlik bir vaqtda nechta biznes bilan ishlaydi (standart 10)"),
                          ("general.theme_default", "Standart mavzu", "choice:light,dark", ""), ("security.lockout_attempts", "Bloklash: urinishlar soni", "int", ""),
                          ("security.lockout_minutes", "Bloklash: daqiqa", "int", "")]),
    "kalitlar": ("API kalitlar", [("meta.app_id", "Meta (Instagram) App ID", "text", "Yo'riqnoma §Meta"), ("meta.app_secret", "Meta App Secret", "secret", ""),
                                  ("google.client_id", "Google Client ID", "text", "Yo'riqnoma §Google"), ("google.client_secret", "Google Client Secret", "secret", ""),
                                  ("youtube.api_key", "YouTube Data API kaliti", "secret", ""), ("telegram.api_id", "Telegram API ID (Telethon)", "text", ""),
                                  ("telegram.api_hash", "Telegram API Hash", "secret", ""), ("telegram.agency_bot_token", "Mijoz kabineti boti tokeni", "secret", "@BotFather"),
                                  ("scrapecreators.api_key", "ScrapeCreators kaliti", "secret", ""), ("worker.cloudflare_url", "Cloudflare Worker manzili", "text", "https://smm-links.<akkaunt>.workers.dev"),
                                  ("worker.admin_token", "Worker admin tokeni", "secret", ""),
                                  ("oauth.callback_url", "OAuth callback bazasi (ixtiyoriy)", "text", "Faqat Worker ishlamasa: http://localhost:8000 (serverning o'zidan ulaning)"), ("r2.account_id", "R2 Account ID (ixtiyoriy)", "text", ""),
                                  ("r2.access_key_id", "R2 Access Key ID", "secret", ""), ("r2.secret_access_key", "R2 Secret", "secret", ""), ("r2.bucket", "R2 Bucket", "text", "")]),
    "yigish": ("Ma'lumot yig'ish", [("collect.enabled", "Yig'ish yoqilgan", "bool", ""), ("collect.schedule", "Kunlik vaqtlar (HH:MM, vergul bilan)", "list", ""),
                                    ("collect.history_days", "Tarixiy import (kun)", "int", ""), ("competitors.light_per_day", "Raqobatchi: yengil tekshiruv/kun", "int", ""),
                                    ("competitors.heavy_per_week", "Raqobatchi: to'liq/hafta", "int", "")]),
    "provayder": ("Provayderlar", [("providers.priority", "Ustuvorlik (JSON)", "json", '{"youtube":["youtube_data_api","scrapecreators"]}'), ("providers.quota_switch_pct", "Kvota almashish chegarasi %", "int", ""),
                                   ("providers.youtube_data_api.daily_quota", "YouTube kunlik kvota", "int", "Standart 10 000"), ("scrapecreators.mode", "ScrapeCreators rejimi", "choice:free,paid", ""),
                                   ("scrapecreators.daily_cap", "ScrapeCreators: kunlik limit", "int", ""), ("scrapecreators.monthly_cap", "ScrapeCreators: oylik limit", "int", ""),
                                   ("scrapecreators.credit_warn_threshold", "Kredit ogohlantirish chegarasi", "int", ""), ("telethon.daily_request_cap", "Telethon: kunlik so'rov limiti", "int", "Ban'dan himoya"),
                                   ("telethon.min_delay_sec", "Telethon: min kutish (s)", "int", ""), ("telethon.max_delay_sec", "Telethon: max kutish (s)", "int", "")]),
    "ai": ("AI router", [("ai.mode", "AI rejimi", "choice:free_first,openai_first,openai_only", "free_first = avval bepul kalitlar; openai_first = avval OpenAI; openai_only = FAQAT OpenAI Platform (barqaror va sifatli, pullik)"),
                         ("ai.openai.model_complex", "OpenAI: murakkab vazifalar modeli", "text", "Ssenariy, reja, brend, reklama uchun (masalan: gpt-4o). Oddiy vazifalar «Modellar» dagi openai modelini ishlatadi"),
                         ("ai.routes", "Vazifa → provayder yo'nalishi (JSON)", "json", "[provayder, pullik_mi]"), ("ai.models", "Modellar (JSON)", "json", ""),
                         ("ai.openai.fallback", "OpenAI zaxirasi (bepul AI ishlamasa)", "bool", "AI kalitlari bo'limida «openai» kaliti qo'shilgan bo'lsa ishlaydi"), ("ai.openai.monthly_budget_usd", "OpenAI oylik byudjet ($, 0 = cheklanmagan)", "int", "Standart: 10"),
                         ("ai.paid.enabled", "Pullik AI (Claude) yoqilgan", "bool", "Standart: O'CHIQ"), ("ai.paid.policy", "Pullik AI siyosati", "choice:only_when_free_exhausted,quality_tasks,always", ""),
                         ("ai.paid.monthly_budget_usd", "Pullik AI oylik byudjet ($)", "int", ""), ("ai.paid.claude_key", "Claude API kaliti", "secret", ""), ("stt.min_confidence", "STT minimal ishonch", "text", "")]),
    "nashr": ("Nashr", [("publish.use_r2", "Vaqtinchalik hosting", "choice:auto,worker_kv,r2", "auto: avval Worker KV, kerak bo'lsa R2"), ("publish.late_policy_min", "Kechikish siyosati (daqiqa)", "int", ""),
                        ("publish.max_attempts", "Maksimal urinish", "int", ""), ("youtube.upload_daily_cap", "YouTube kunlik yuklash limiti", "int", "10 000 kvotada ~6"), ("publish.r2.max_gb", "R2 hajm chegarasi (GB)", "int", "")]),
    "zaxira": ("Zaxira", [("backup.keep_days", "Zaxira saqlash (kun)", "int", ""), ("backup.dir", "Zaxira papkasi", "text", ""), ("media.retention_days", "Media saqlash (kun)", "int", "")]),
}


KEYS = {key: (label, kind, hlp) for _t, (_n, rows) in TABS.items() for key, label, kind, hlp in rows}


class Sec:
    """Sozlamalar bo'limi: sarlavha, nima uchun kerakligi, yo'riqnoma, kalitlar va (bo'lsa) tekshirish tugmasi."""

    def __init__(self, title, desc, keys, guide=None, test=None, service=False):
        self.title, self.desc, self.keys, self.guide, self.test, self.service = title, desc, keys, guide, test, service


# (kalit, nom, ikonka, qisqa izoh, bo'limlar)
CATEGORIES = [
    ("brend", "Brend va tizim", "palette", "Tizim nomi, logotip, rang, xavfsizlik", [
        Sec("Manzil va chegaralar", "Tashqi manzil mijozga yuboriladigan hisobot havolasi va telefon ilovasi uchun kerak.", ["general.public_url", "agency.max_businesses"], "00-mobil"),
        Sec("Xavfsizlik", "Parolni ketma-ket noto'g'ri kiritganda hisob vaqtincha bloklanadi.", ["security.lockout_attempts", "security.lockout_minutes"], "00-rol-admin")]),
    ("xizmatlar", "Tashqi xizmatlar", "plug", "Instagram, YouTube, Telegram, Cloudflare, ScrapeCreators", [
        Sec("Instagram (Meta)", "Instagram akkauntini ulash, statistikani olish va post joylash uchun. Meta ilovasi (App) kerak.", ["meta.app_id", "meta.app_secret"], "02-meta-instagram", service=True),
        Sec("YouTube (Google)", "YouTube kanalini ulash (OAuth) va ochiq ma'lumotlarni olish uchun.", ["google.client_id", "google.client_secret", "youtube.api_key"], "03-google-youtube", "youtube", True),
        Sec("Telegram", "Telethon (kanal statistikasi) va mijoz kabineti boti. Kanalga post joylaydigan bot «Ulanishlar»da qo'shiladi.", ["telegram.api_id", "telegram.api_hash", "telegram.agency_bot_token"], "04-telegram", "agency_bot", True),
        Sec("Cloudflare Worker", "Qisqa havolalar, bosishlarni hisoblash va OAuth qaytish manzili uchun (bepul).", ["worker.cloudflare_url", "worker.admin_token", "oauth.callback_url"], "05-cloudflare-worker", "worker", True),
        Sec("Cloudflare R2 (fayllar)", "Katta rasm/video fayllarni vaqtincha saqlash (Instagram/YouTube'ga yuborish uchun).", ["r2.account_id", "r2.access_key_id", "r2.secret_access_key", "r2.bucket"], "05-cloudflare-worker", "r2", True),
        Sec("ScrapeCreators", "Raqobatchilar va ochiq ma'lumot uchun zaxira provayder (pullik, kredit bilan).", ["scrapecreators.api_key"], "07-scrapecreators", "scrapecreators", True)]),
    ("ai", "AI", "spark", "AI rejimi, OpenAI, kalitlar", [
        Sec("AI rejimi va byudjet", "Qaysi AI avval ishlashi va oylik xarajat chegarasi.", ["ai.mode", "ai.openai.fallback", "ai.openai.monthly_budget_usd", "ai.openai.model_complex", "ai.paid.enabled", "ai.paid.policy", "ai.paid.monthly_budget_usd", "ai.paid.claude_key"], "06-ai-kalitlar"),
        Sec("Ilg'or: yo'nalish va modellar", "Faqat nima qilayotganingizni bilsangiz o'zgartiring.", ["ai.routes", "ai.models", "stt.min_confidence"], "06-ai-kalitlar")]),
    ("malumot", "Ma'lumot yig'ish", "pulse", "Jadval, raqobatchilar, provayderlar", [
        Sec("Yig'ish jadvali", "Statistika qaysi vaqtlarda avtomatik yig'iladi.", ["collect.enabled", "collect.schedule", "collect.history_days"], "13-yangi-imkoniyatlar"),
        Sec("Raqobatchilar", "Raqobatchi akkauntlarini tekshirish tezligi.", ["competitors.light_per_day", "competitors.heavy_per_week"], "13-yangi-imkoniyatlar"),
        Sec("Provayderlar va limitlar", "Ma'lumot manbalari ustuvorligi va kunlik/oylik chegaralar (ban va xarajatdan himoya).", ["providers.priority", "providers.quota_switch_pct", "providers.youtube_data_api.daily_quota", "scrapecreators.mode", "scrapecreators.daily_cap", "scrapecreators.monthly_cap", "scrapecreators.credit_warn_threshold", "telethon.daily_request_cap", "telethon.min_delay_sec", "telethon.max_delay_sec"], "07-scrapecreators")]),
    ("nashr", "Nashr va zaxira", "send", "Nashr qoidalari, zaxira nusxa", [
        Sec("Nashr", "Post chiqarish siyosati: kechikish, urinishlar, hosting.", ["publish.use_r2", "publish.late_policy_min", "publish.max_attempts", "youtube.upload_daily_cap", "publish.r2.max_gb"], "05-cloudflare-worker"),
        Sec("Zaxira va saqlash", "Ma'lumotlar bazasi zaxirasi qancha saqlanishi.", ["backup.keep_days", "backup.dir", "media.retention_days"], "09-zaxira")]),
]
CAT_KEYS = {c[0]: [k for sec in c[4] for k in sec.keys] for c in CATEGORIES}


def _to_form_value(kind, key):
    v = ss.get_setting(key, "")
    if kind == "secret":
        return ""
    if kind == "list":
        return ", ".join(v) if isinstance(v, list) else v
    if kind == "json":
        return json.dumps(v, ensure_ascii=False, indent=1)
    return v


def _build_form(cat, data=None):
    fields = {}
    for key in CAT_KEYS[cat]:
        label, kind, hlp = KEYS[key]
        name = key.replace(".", "__")
        if kind == "bool":
            f = forms.BooleanField(label=label, required=False, help_text=hlp)
        elif kind == "int":
            f = forms.IntegerField(label=label, required=False, help_text=hlp)
        elif kind == "json":
            f = forms.CharField(label=label, required=False, widget=forms.Textarea(attrs={"rows": 6}), help_text=hlp)
        elif kind.startswith("choice:"):
            f = forms.ChoiceField(label=label, choices=[(x, x) for x in kind[7:].split(",")], required=False, help_text=hlp)
        elif kind == "secret":
            cur = ss.masked(key)
            f = forms.CharField(label=label, required=False, widget=forms.PasswordInput(render_value=False, attrs={"placeholder": cur or "kiritilmagan", "autocomplete": "new-password"}),
                                help_text=("Hozirgi: " + cur + " · " if cur else "") + "Bo'sh qoldirilsa o'zgarmaydi. " + hlp)
        else:
            f = forms.CharField(label=label, required=False, help_text=hlp)
        fields[name] = f
    form = type("SF", (forms.Form,), fields)(data)
    if data is None:
        for key in CAT_KEYS[cat]:
            form.fields[key.replace(".", "__")].initial = _to_form_value(KEYS[key][1], key)
    return form


def _sec_status(sec):
    """Xizmat kartasi holati: barcha kalit kiritilgan -> ok, ba'zisi -> partial, hech biri -> empty."""
    vals = [bool(ss.get_setting(k, "")) for k in sec.keys if KEYS[k][1] in ("secret", "text") and not k.startswith("oauth.") and k != "r2.account_id"]
    return "ok" if vals and all(vals) else "partial" if any(vals) else "empty"


def _brand_json():
    from apps.web.spa import brand_payload
    return brand_payload()


@login_required
@require_permission("settings.view")
def settings_home(request):
    cat = request.GET.get("tab", "brend")
    cat = {"umumiy": "brend", "kalitlar": "xizmatlar", "yigish": "malumot", "provayder": "malumot", "zaxira": "nashr"}.get(cat, cat)
    if cat not in CAT_KEYS:
        raise Http404
    can_edit = perms.can(request.user, "settings.configure", None)
    form = _build_form(cat, request.POST or None)
    if request.method == "POST":
        if not can_edit:
            return HttpResponseForbidden("Ruxsat yo'q")
        if form.is_valid():
            for key in CAT_KEYS[cat]:
                label, kind, _h = KEYS[key]
                v = form.cleaned_data.get(key.replace(".", "__"))
                if kind == "secret":
                    if v:
                        ss.set_setting(key, v.strip(), user=request.user)
                    continue
                if kind == "int":
                    v = v if v is not None else ss.get_setting(key, 0)
                elif kind == "list":
                    v = [x.strip() for x in (v or "").split(",") if x.strip()]
                elif kind == "json":
                    try:
                        v = json.loads(v) if v else ss.get_setting(key)
                    except ValueError:
                        messages.error(request, f"«{label}»: JSON noto'g'ri, saqlanmadi.")
                        continue
                elif kind == "text" and key == "stt.min_confidence":
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        continue
                ss.set_setting(key, v, user=request.user)
            messages.success(request, "Sozlamalar saqlandi.")
            return redirect(f"/sozlamalar/?tab={cat}")
    guides = {g["slug"]: g["title"] for g in __import__("apps.web.views_core", fromlist=["_guides"])._guides()}
    sections = [{"title": sec.title, "desc": sec.desc, "fields": [k.replace(".", "__") for k in sec.keys], "status": _sec_status(sec) if sec.service else None,
                 "guide": {"slug": sec.guide, "title": guides.get(sec.guide, "Yo'riqnoma")} if sec.guide else None,
                 "test": ({"label": "Ulanishni tekshirish", "post": "/cloudflare/sinov/" if sec.test == "r2" else f"/sozlamalar/tekshir/{sec.test}/"} if sec.test and can_edit else None)}
                for sec in dict((c[0], c[4]) for c in CATEGORIES)[cat]]
    extra = []
    if cat == "ai":
        extra.append(_openai_block())
        keys = AIKey.objects.order_by("provider", "alias")
        extra.append(ui.table("AI kalitlar (rotatsiya)", ["Provayder", "Nomi", "Holat", "Oxirgi xato", "", ""],
                              [[k.provider, k.alias, ui.badge("Faol" if k.enabled else "O'chiq", "active" if k.enabled else "paused", f"sovish: {ui.dt(k.cooldown_until)}" if k.cooldown_until else None), (k.last_error or "—")[:90],
                                ui.btn("Tekshirish", f"/sozlamalar/ai-kalit/{k.pk}/tekshir/"), ui.btn("O'chirish", f"/sozlamalar/ai-kalit/{k.pk}/ochir/", "danger", "Kalit o'chirilsinmi?")] for k in keys], "AI kalit qo'shilmagan."))
        if can_edit:
            f = type("KF", (forms.Form,), {"provider": forms.ChoiceField(label="Provayder", choices=[(p, p) for p, _ in AIKey._meta.get_field("provider").choices]),
                                           "alias": forms.CharField(label="Nom (masalan: gemini-1)"), "key": forms.CharField(label="Kalit", widget=forms.PasswordInput)})()
            extra.append(ui.form_block(f, "AI kalit qo'shish", "Qo'shish va tekshirish", action="/sozlamalar/ai-kalit/qoshish/"))
    return spa.respond(request, {
        "kind": "settings", "tab": cat, "can_edit": bool(can_edit), "tabs": [{"key": c[0], "label": c[1], "icon": c[2], "desc": c[3]} for c in CATEGORIES],
        "brand": _brand_json() if cat == "brend" else None, "form": spa.form_schema(form), "sections": sections, "extra": [spa.block_json(b) for b in extra]})


@login_required
@require_POST
@require_permission("settings.configure")
def brand_save(request):
    """Tizim nomi, rang, standart mavzu va logotip (yuklash/olib tashlash)."""
    import os
    from pathlib import Path

    from django.conf import settings as dj
    name = (request.POST.get("name") or "").strip()[:60]
    color = (request.POST.get("color") or "").strip()
    theme = request.POST.get("theme")
    if name:
        ss.set_setting("general.system_name", name, user=request.user)
    if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        ss.set_setting("general.brand_color", color.upper(), user=request.user)
    if theme in ("light", "dark"):
        ss.set_setting("general.theme_default", theme, user=request.user)
    if request.POST.get("remove_logo") == "1":
        ss.set_setting("general.agency_logo", "", user=request.user)
    f = request.FILES.get("logo")
    if f:
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg") or f.size > 2 * 1024 * 1024:
            messages.error(request, "Logotip PNG/JPG/WEBP/SVG bo'lishi va 2 MB dan oshmasligi kerak.")
            return redirect("/sozlamalar/?tab=brend")
        d = Path(dj.MEDIA_ROOT) / "brand"
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("logo.*"):
            old.unlink()
        dest = d / f"logo{ext}"
        with open(dest, "wb") as out:
            for ch in f.chunks():
                out.write(ch)
        ss.set_setting("general.agency_logo", f"brand/logo{ext}", user=request.user)
    audit("setting.brand", user=request.user, target="brand")
    messages.success(request, "Brend sozlamalari saqlandi.")
    return redirect("/sozlamalar/?tab=brend")


@login_required
@require_POST
@require_permission("settings.configure")
def ai_key_add(request):
    from apps.ai_router import providers as aip
    p, alias, key = request.POST.get("provider", ""), request.POST.get("alias", "").strip(), request.POST.get("key", "").strip()
    if not (p and alias and key):
        messages.error(request, "Barcha maydonlarni to'ldiring.")
    elif AIKey.objects.filter(provider=p, alias=alias).exists():
        messages.error(request, "Bunday nom allaqachon bor.")
    elif (prob := aip.key_format_problem(p, key)):
        messages.error(request, f"Kalit saqlanmadi. {prob}")
    else:
        ok, info = aip.validate_key(p, key)
        if ok is False:
            messages.error(request, f"Kalit saqlanmadi: {info}")
        else:
            k = AIKey(provider=p, alias=alias)
            k.set_secret(key)
            k.save()
            audit("ai_key.add", user=request.user, target=f"{p}/{alias}")
            if ok:
                messages.success(request, f"Kalit qo'shildi va tekshirildi: ishlaydi ({p}).")
            else:
                messages.warning(request, f"Kalit qo'shildi (shifrlangan), lekin tekshirib bo'lmadi: {info}")
    return redirect("/sozlamalar/?tab=ai")


@login_required
@require_POST
@require_permission("settings.configure")
def ai_key_test(request, pk):
    from apps.ai_router import providers as aip
    k = get_object_or_404(AIKey, pk=pk)
    ok, info = aip.validate_key(k.provider, k.secret())
    if ok:
        k.fail_streak, k.cooldown_until, k.last_error, k.last_ok_at = 0, None, "", timezone.now()
        k.save(update_fields=["fail_streak", "cooldown_until", "last_error", "last_ok_at"])
        messages.success(request, f"«{k.alias}»: {info} Sovish va xato tozalandi.")
    else:
        messages.error(request, f"«{k.alias}»: {info}")
    return redirect("/sozlamalar/?tab=ai")


@login_required
@require_POST
@require_permission("settings.configure")
def ai_key_delete(request, pk):
    k = get_object_or_404(AIKey, pk=pk)
    audit("ai_key.delete", user=request.user, target=f"{k.provider}/{k.alias}")
    k.delete()
    return redirect("/sozlamalar/?tab=ai")


@login_required
@require_POST
@require_permission("settings.configure")
def setting_test(request, what):
    import requests
    try:
        if what == "worker":
            from apps.links.services import client, sync_clicks
            r = client().status()
            try:
                sync_clicks()   # Tizim holati sahifasidagi Worker holatini ham yangilaydi
            except Exception:  # noqa: BLE001
                pass
            messages.success(request, f"Worker ishlayapti (versiya {r.get('version')}).") if r.get("ok") else messages.error(request, "Worker javob berdi, lekin ok=false.")
        elif what == "youtube":
            key = ss.get_secret("youtube.api_key")
            r = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "id", "id": "UC_x5XG1OV2P6uZZ5FSM9Ttw", "key": key}, timeout=15)
            (messages.success if r.status_code == 200 else messages.error)(request, "YouTube kaliti ishlaydi." if r.status_code == 200 else f"YouTube: {r.status_code} {r.text[:120]}")
        elif what == "scrapecreators":
            key = ss.get_secret("scrapecreators.api_key")
            r = requests.get("https://api.scrapecreators.com/v1/credit-balance", headers={"x-api-key": key}, timeout=15)
            (messages.success if r.status_code == 200 else messages.error)(request, f"ScrapeCreators: {r.text[:120]}")
        elif what == "agency_bot":
            tok = ss.get_secret("telegram.agency_bot_token")
            r = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=15).json()
            messages.success(request, f"Bot: @{r['result']['username']}") if r.get("ok") else messages.error(request, "Bot tokeni noto'g'ri.")
        else:
            raise Http404
    except Http404:
        raise
    except Exception as e:  # noqa: BLE001
        messages.error(request, getattr(e, "user_message_uz", None) or f"Tekshiruvda xato: {e}")
    return redirect("/sozlamalar/?tab=xizmatlar")


# ---------------- Foydalanuvchilar ----------------
class UserForm(forms.ModelForm):
    password = forms.CharField(label="Parol", required=False, widget=forms.PasswordInput(render_value=False), help_text="Yangi foydalanuvchi uchun majburiy; tahrirda bo'sh = o'zgarmaydi. Kamida 8 belgi.")

    class Meta:
        model = User
        fields = ["username", "full_name", "email", "telegram_id", "is_admin", "is_active"]


@login_required
@require_permission("users.view")
def user_list(request):
    rows = []
    for u in User.objects.order_by("username"):
        acc = ", ".join(f"{a.business.name if a.business else 'Hammasi'}: {a.role.name}" for a in u.accesses.select_related("business", "role"))
        rows.append([ui.link(u.username, f"/foydalanuvchilar/{u.pk}/"), u.full_name, "Admin" if u.is_admin else acc or "—", ui.badge("Faol" if u.is_active else "O'chiq", "active" if u.is_active else "paused"), ui.dt(u.last_login)])
    tb = [{"label": "Yangi foydalanuvchi", "url": "/foydalanuvchilar/yangi/", "cls": "primary"}, {"label": "Rollar", "url": "/foydalanuvchilar/rollar/"},
          {"label": "Mijoz bot taklifnomalari", "url": "/foydalanuvchilar/mijoz-bot/"}, {"label": "Audit jurnali", "url": "/audit/"}] if perms.can(request.user, "users.create", None) else []
    return ui.page(request, "Foydalanuvchilar", [ui.table(None, ["Login", "Ism", "Rol / kirish", "Holat", "Oxirgi kirish"], rows)], toolbar=tb)


def _pwd_ok(p):
    from django.contrib.auth.password_validation import validate_password
    validate_password(p)


@login_required
@require_permission("users.create")
def user_new(request):
    form = UserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pw = form.cleaned_data["password"]
        try:
            if not pw:
                raise ValueError("Yangi foydalanuvchi uchun parol kerak.")
            _pwd_ok(pw)
        except Exception as e:  # noqa: BLE001
            form.add_error("password", getattr(e, "messages", [str(e)]))
        else:
            u = form.save(commit=False)
            u.set_password(pw)
            u.save()
            audit("user.create", user=request.user, target=u.username)
            messages.success(request, "Foydalanuvchi yaratildi. Endi biznes va rol biriktiring.")
            return redirect("user_detail", pk=u.pk)
    return ui.form_page(request, "Yangi foydalanuvchi", form, back="/foydalanuvchilar/")


@login_required
@require_permission("users.view")
def user_detail(request, pk):
    u = get_object_or_404(User, pk=pk)
    can = perms.can(request.user, "users.edit", None)
    acc = [[a.business.name if a.business else "Barcha bizneslar", a.role.name, ui.btn("Olib tashlash", f"/foydalanuvchilar/{u.pk}/kirish/{a.pk}/ochir/", "danger") if can else ""] for a in u.accesses.select_related("business", "role")]
    blocks = [ui.kv("Ma'lumot", [("Login", u.username), ("Ism", u.full_name), ("Telegram ID", u.telegram_id), ("Admin", "Ha" if u.is_admin else "Yo'q"), ("Faol", "Ha" if u.is_active else "Yo'q")]),
              ui.table("Biznes va rol", ["Biznes", "Rol", ""], acc, "Hech qaysi bizneska biriktirilmagan.")]
    if can:
        f = type("AF", (forms.Form,), {"business": forms.ModelChoiceField(label="Biznes", queryset=Business.objects.filter(archived_at__isnull=True), required=False, empty_label="— Barcha bizneslar —"),
                                       "role": forms.ModelChoiceField(label="Rol", queryset=Role.objects.all())})()
        blocks.append(ui.form_block(f, "Kirish berish", "Biriktirish", action=f"/foydalanuvchilar/{u.pk}/kirish/"))
        blocks.append(ui.form_block(UserForm(instance=u), "Tahrirlash", "Saqlash", action=f"/foydalanuvchilar/{u.pk}/tahrir/"))
    return ui.page(request, u.display, blocks, toolbar=[{"label": "Orqaga", "url": "/foydalanuvchilar/"}])


@login_required
@require_POST
@require_permission("users.edit")
def user_edit(request, pk):
    u = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST, instance=u)
    if form.is_valid():
        try:
            guard_admin_change(User.objects.get(pk=u.pk), deactivating=not form.cleaned_data["is_active"], demoting=not form.cleaned_data["is_admin"])
            pw = form.cleaned_data["password"]
            if pw:
                _pwd_ok(pw)
            obj = form.save(commit=False)
            if pw:
                obj.set_password(pw)
            obj.save()
            bump_permissions(obj)
            audit("user.edit", user=request.user, target=u.username)
            messages.success(request, "Saqlandi.")
        except PermissionError as e:
            messages.error(request, str(e))
        except Exception as e:  # noqa: BLE001
            messages.error(request, "; ".join(getattr(e, "messages", [str(e)])))
    else:
        messages.error(request, "Maydonlarni tekshiring.")
    return redirect("user_detail", pk=u.pk)


@login_required
@require_POST
@require_permission("users.edit")
def user_access_add(request, pk):
    u = get_object_or_404(User, pk=pk)
    role = get_object_or_404(Role, pk=request.POST.get("role"))
    bid = request.POST.get("business")
    if bid:
        UserBusinessAccess.objects.update_or_create(user=u, business_id=int(bid), defaults={"role": role, "all_flag": False})
    else:
        UserBusinessAccess.objects.update_or_create(user=u, business=None, defaults={"role": role, "all_flag": True})
    bump_permissions(u)
    audit("user.access", user=request.user, target=u.username, detail={"business": bid, "role": role.name})
    return redirect("user_detail", pk=u.pk)


@login_required
@require_POST
@require_permission("users.edit")
def user_access_delete(request, pk, aid):
    a = get_object_or_404(UserBusinessAccess, pk=aid, user_id=pk)
    a.delete()
    bump_permissions()
    return redirect("user_detail", pk=pk)


# ---------------- Rollar ----------------
@login_required
@require_permission("users.view")
def role_list(request):
    rows = [[ui.link(r.name, f"/foydalanuvchilar/rollar/{r.pk}/"), r.description, "Tizim" if r.is_system else "—", r.permissions.count()] for r in Role.objects.order_by("name")]
    blocks = [ui.table(None, ["Rol", "Tavsif", "Tur", "Ruxsatlar"], rows)]
    if perms.can(request.user, "users.create", None):
        f = type("RF", (forms.Form,), {"name": forms.CharField(label="Rol nomi", max_length=60), "description": forms.CharField(label="Tavsif", required=False)})()
        blocks.append(ui.form_block(f, "Yangi rol", "Yaratish", action="/foydalanuvchilar/rollar/yangi/"))
    return ui.page(request, "Rollar", blocks, toolbar=[{"label": "Orqaga", "url": "/foydalanuvchilar/"}])


@login_required
@require_POST
@require_permission("users.create")
def role_new(request):
    name = request.POST.get("name", "").strip()
    if name and not Role.objects.filter(name=name).exists():
        r = Role.objects.create(name=name, description=request.POST.get("description", ""))
        return redirect("role_detail", pk=r.pk)
    messages.error(request, "Nom bo'sh yoki band.")
    return redirect("role_list")


@login_required
@require_permission("users.view")
def role_detail(request, pk):
    r = get_object_or_404(Role, pk=pk)
    can = perms.can(request.user, "users.edit", None)
    if request.method == "POST":
        if not can:
            return HttpResponseForbidden("Ruxsat yo'q")
        codes = {c for c in request.POST.getlist("codes") if c.split(".")[0] in MODULES and c.split(".")[1] in ACTIONS}
        set_role_permissions(r, codes)
        audit("role.permissions", user=request.user, target=r.name, detail={"count": len(codes)})
        messages.success(request, "Ruxsatlar saqlandi.")
        return redirect("role_detail", pk=r.pk)
    have = set(r.permissions.values_list("code", flat=True))
    return spa.respond(request, {
        "kind": "role_matrix", "role": {"id": r.pk, "name": r.name, "is_system": bool(r.is_system), "description": r.description}, "can": bool(can),
        "modules": [[k, v] for k, v in MODULES.items() if k != "approvals"], "actions": [[k, v] for k, v in ACTIONS.items() if k != "approve"],
        "have": sorted(have)})


@login_required
@require_POST
@require_permission("users.delete")
def role_delete(request, pk):
    try:
        delete_role(get_object_or_404(Role, pk=pk))
        messages.success(request, "Rol o'chirildi.")
    except PermissionError as e:
        messages.error(request, str(e))
        return redirect("role_detail", pk=pk)
    return redirect("role_list")


# ---------------- Mijoz boti ----------------
@login_required
@require_permission("users.create")
def client_bot(request):
    new_code = request.session.pop("new_invite", None)
    f = type("IF", (forms.Form,), {"business": forms.ModelMultipleChoiceField(label="Bizneslar", queryset=Business.objects.filter(archived_at__isnull=True)), "label": forms.CharField(label="Izoh (mijoz nomi)", required=False),
                                   "hours": forms.IntegerField(label="Amal qilish muddati (soat)", initial=72, min_value=1, max_value=720)})()
    blocks = []
    if new_code:
        blocks.append({"type": "html", "title": "Taklif kodi (faqat hozir ko'rinadi)", "html": f'<p>Mijoz mijoz-kabinet botiga <code>/start {new_code}</code> yuborsin.</p>'})
    blocks += [ui.form_block(f, "Yangi taklifnoma", "Kod yaratish", action="/foydalanuvchilar/mijoz-bot/yangi/"),
               ui.table("Taklifnomalar", ["Izoh", "Bizneslar", "Muddati", "Ishlatilgan"], [[i.label, len(i.business_ids), ui.dt(i.expires_at), ui.dt(i.used_at)] for i in ClientInvite.objects.order_by("-created_at")[:20]]),
               ui.table("Mijoz bot foydalanuvchilari", ["Ism", "Telegram ID", "Bizneslar", "Holat", ""],
                        [[c.name, c.tg_user_id, len(c.business_ids), ui.badge("Faol" if c.active else "O'chiq", "active" if c.active else "paused"), ui.btn("O'chirish" if c.active else "Yoqish", f"/foydalanuvchilar/mijoz-bot/{c.pk}/almashtir/")] for c in ClientBotUser.objects.all()])]
    return ui.page(request, "Mijoz kabineti boti", blocks, toolbar=[{"label": "Orqaga", "url": "/foydalanuvchilar/"}])


@login_required
@require_POST
@require_permission("users.create")
def client_invite_new(request):
    ids = [int(x) for x in request.POST.getlist("business") if x.isdigit() and perms.has_business(request.user, int(x))]
    if not ids:
        messages.error(request, "Kamida bitta biznes tanlang.")
    else:
        request.session["new_invite"] = create_invite(ids, request.user, request.POST.get("label", ""), int(request.POST.get("hours") or 72))
    return redirect("client_bot")


@login_required
@require_POST
@require_permission("users.edit")
def client_user_toggle(request, pk):
    c = get_object_or_404(ClientBotUser, pk=pk)
    c.active = not c.active
    c.save(update_fields=["active"])
    return redirect("client_bot")


def _openai_block() -> dict:
    from decimal import Decimal
    from django.db.models import Count, Sum
    from django.utils import timezone
    from apps.ai_router.models import AIUsageLog
    start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = AIUsageLog.objects.filter(at__gte=start)
    rows = list(q.values("provider").annotate(n=Count("id"), c=Sum("cost_usd")).order_by("-n"))
    budget = Decimal(str(ss.get_setting("ai.openai.monthly_budget_usd", 10) or 0))
    oa = next((r for r in rows if r["provider"] == "openai"), None)
    spent = (oa["c"] or Decimal(0)) if oa else Decimal(0)
    mode = ss.get_setting("ai.mode", "free_first")
    has_key = AIKey.objects.filter(provider="openai", enabled=True).exists()
    lines = [f"<b>Joriy rejim:</b> {dict(free_first='Avval bepul kalitlar', openai_first='Avval OpenAI', openai_only='Faqat OpenAI Platform')[mode] if mode in ('free_first', 'openai_first', 'openai_only') else mode}",
             f"<b>OpenAI kaliti:</b> {'qo`shilgan ✅' if has_key else 'YO`Q ❌ — pastdagi «AI kalit qo`shish» da provayder = openai tanlang'}",
             f"<b>Shu oy OpenAI xarajati:</b> ${spent:.2f}" + (f" / ${budget} byudjet ({float(spent / budget * 100):.0f}%)" if budget > 0 else " (byudjet cheklanmagan)")]
    if rows:
        lines.append("<b>Shu oy so'rovlar:</b> " + ", ".join(f"{r['provider']}: {r['n']}" for r in rows))
    if mode == "openai_only" and not has_key:
        lines.append("<span style='color:#dc2626'><b>Diqqat:</b> rejim «faqat OpenAI», lekin kalit yo'q — AI ishlamaydi!</span>")
    return {"type": "html", "title": "OpenAI Platform holati", "html": "<br>".join(lines).replace("`", "&#x27;")}
