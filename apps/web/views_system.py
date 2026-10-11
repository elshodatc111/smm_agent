"""Tizim holati, sozlamalar, foydalanuvchilar/rollar, mijoz boti taklifnomalari."""
from __future__ import annotations

import json

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
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
from . import ui

# ---------------- Tizim holati ----------------


@login_required
@require_permission("system_health.view")
def health(request):
    snap = hs.snapshot()
    return render(request, "health.html", {"s": snap})


@login_required
@require_permission("system_health.view")
def health_partial(request):
    return render(request, "partials/health_body.html", {"s": hs.snapshot()})


@login_required
@require_permission("system_health.view")
def job_list(request):
    qs = Job.objects.order_by("-created_at")
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    page = Paginator(qs, 50).get_page(request.GET.get("p"))
    rows = [[j.pk, j.type, j.queue, ui.badge(j.status, j.status), j.attempts, ui.dt(j.created_at), (j.last_error or "")[:100] or "—",
             ui.btn("Qayta", f"/tizim/vazifalar/{j.pk}/qayta/") if j.status in ("failed", "dead") else ""] for j in page]
    chips = "".join(f'<a class="pill" href="?status={s}">{s}</a> ' for s in ("pending", "running", "done", "failed"))
    return ui.page(request, "Vazifalar navbati", [{"type": "html", "html": chips + '<a class="pill" href="?">hammasi</a>'}, ui.table(None, ["ID", "Tur", "Navbat", "Holat", "Urinish", "Yaratilgan", "Xato", ""], rows)])


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
    "ai": ("AI", [("ai.primary", "Asosiy AI provayder", "choice:openai,claude", "Hamma vazifalar shu provayderdan boshlanadi (pastdagi vazifa sozlamasi o'zgartirmasa)"),
                         ("ai.fallback", "Zaxira", "choice:auto,none", "auto = asosiy ishlamasa ikkinchisiga o'tadi (kaliti qo'shilgan bo'lsa); none = o'tmaydi"),
                         ("ai.task.long_uz", "Vazifa: Matn (post, reja, ssenariy)", "choice:auto,openai,claude", "auto = asosiy provayder"),
                         ("ai.task.classify", "Vazifa: Tasnif (izoh/xabar turi)", "choice:auto,openai,claude", "auto = asosiy provayder"),
                         ("ai.task.vision", "Vazifa: Rasm/video tahlili", "choice:auto,openai,claude", "auto = asosiy provayder"),
                         ("ai.task.brand_profile", "Vazifa: Brend profili", "choice:auto,openai,claude", "auto = asosiy provayder"),
                         ("ai.task.script_review", "Vazifa: Ssenariy bahosi", "choice:auto,openai,claude", "auto = asosiy provayder"),
                         ("ai.task.comment_reply", "Vazifa: Mijozga javob", "choice:auto,openai,claude", "auto = asosiy provayder"),
                         ("ai.task.why_worked", "Vazifa: Nega ishladi tahlili", "choice:auto,openai,claude", "auto = asosiy provayder"),
                         ("ai.task.ad_plan", "Vazifa: Reklama tahlili", "choice:auto,openai,claude", "auto = asosiy provayder"),
                         ("ai.models", "Modellar (JSON)", "json", '{"openai": "gpt-4o-mini", "claude": "claude-sonnet-4-5", "openai_stt": "whisper-1"}'),
                         ("ai.openai.model_complex", "OpenAI: murakkab vazifalar modeli", "text", "Ssenariy, reja, brend, reklama uchun (masalan: gpt-4o)"),
                         ("ai.claude.model_complex", "Claude: murakkab vazifalar modeli", "text", "Bo'sh = oddiy Claude modeli"),
                         ("stt.min_confidence", "Ovozdan matn: minimal ishonch", "text", "")]),
    "nashr": ("Nashr", [("publish.use_r2", "Vaqtinchalik hosting", "choice:auto,worker_kv,r2", "auto: avval Worker KV, kerak bo'lsa R2"), ("publish.late_policy_min", "Kechikish siyosati (daqiqa)", "int", ""),
                        ("publish.max_attempts", "Maksimal urinish", "int", ""), ("youtube.upload_daily_cap", "YouTube kunlik yuklash limiti", "int", "10 000 kvotada ~6"), ("publish.r2.max_gb", "R2 hajm chegarasi (GB)", "int", "")]),
    "zaxira": ("Zaxira", [("backup.keep_days", "Zaxira saqlash (kun)", "int", ""), ("backup.dir", "Zaxira papkasi", "text", ""), ("media.retention_days", "Media saqlash (kun)", "int", "")]),
}


def _to_form_value(kind, key):
    v = ss.get_setting(key, "")
    if kind == "secret":
        return ""
    if kind == "list":
        return ", ".join(v) if isinstance(v, list) else v
    if kind == "json":
        return json.dumps(v, ensure_ascii=False, indent=1)
    return v


def _build_form(tab, data=None):
    fields = {}
    for key, label, kind, hlp in TABS[tab][1]:
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
        for key, label, kind, hlp in TABS[tab][1]:
            form.fields[key.replace(".", "__")].initial = _to_form_value(kind, key)
    return form


@login_required
@require_permission("settings.view")
def settings_home(request):
    tab = request.GET.get("tab", "umumiy")
    if tab not in TABS:
        raise Http404
    can_edit = perms.can(request.user, "settings.configure", None)
    form = _build_form(tab, request.POST or None)
    if request.method == "POST":
        if not can_edit:
            return HttpResponseForbidden("Ruxsat yo'q")
        if form.is_valid():
            for key, label, kind, hlp in TABS[tab][1]:
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
            return redirect(f"/sozlamalar/?tab={tab}")
    tabs = "".join(f'<a class="pill {"active" if k == tab else ""}" href="?tab={k}">{v[0]}</a> ' for k, v in TABS.items())
    tabs += '<a class="pill" href="/sozlamalar/biznes-turlari/">Biznes turlari</a>'
    blocks = [{"type": "html", "html": tabs}, ui.form_block(form, TABS[tab][0], "Saqlash" if can_edit else "Faqat ko'rish")]
    if tab == "ai":
        blocks.insert(1, _openai_block())
        keys = AIKey.objects.order_by("provider", "alias")
        blocks.append(ui.table("AI kalitlar (rotatsiya)", ["Provayder", "Nomi", "Holat", "Oxirgi xato", "", ""],
                               [[k.provider, k.alias, ui.badge("Faol" if k.enabled else "O'chiq", "active" if k.enabled else "paused", f"sovish: {ui.dt(k.cooldown_until)}" if k.cooldown_until else None), (k.last_error or "—")[:80],
                                 ui.btn("Tekshirish", f"/sozlamalar/ai-kalit/{k.pk}/tekshir/"), ui.btn("O'chirish", f"/sozlamalar/ai-kalit/{k.pk}/ochir/", "danger", "Kalit o'chirilsinmi?")] for k in keys], "AI kalit qo'shilmagan."))
        if can_edit:
            blocks.append(ui.form_block(forms.Form(), None))
            f = type("KF", (forms.Form,), {"provider": forms.ChoiceField(label="Provayder", choices=[(p, p) for p, _ in AIKey._meta.get_field("provider").choices]),
                                           "alias": forms.CharField(label="Nom (masalan: openai-1)"), "key": forms.CharField(label="Kalit", widget=forms.PasswordInput)})()
            blocks[-1] = ui.form_block(f, "AI kalit qo'shish", "Qo'shish va tekshirish", action="/sozlamalar/ai-kalit/qoshish/")
    if tab == "kalitlar" and can_edit:
        blocks.append({"type": "actions", "title": "Ulanishni tekshirish", "buttons": [ui.btn("Cloudflare Worker", "/sozlamalar/tekshir/worker/"), ui.btn("ScrapeCreators", "/sozlamalar/tekshir/scrapecreators/"),
                                                                                        ui.btn("YouTube API kaliti", "/sozlamalar/tekshir/youtube/"), ui.btn("Mijoz boti", "/sozlamalar/tekshir/agency_bot/")]})
    return ui.page(request, "Sozlamalar", blocks)


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
            from apps.content.temphost import worker_status
            r = worker_status()
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
    return redirect("/sozlamalar/?tab=kalitlar")


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
    return render(request, "form.html", {"title": "Yangi foydalanuvchi", "form": form, "back": "/foydalanuvchilar/"})


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
    return render(request, "role_matrix.html", {"role": r, "modules": {k: v for k, v in MODULES.items() if k != "approvals"}, "actions": {k: v for k, v in ACTIONS.items() if k != "approve"}, "have": have, "can": can})


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
    """AI holati: asosiy/zaxira provayder, kalitlar, shu oy so'rovlar va taxminiy sarf (tokenlardan hisoblangan)."""
    from django.db.models import Count, Sum
    from django.utils import timezone
    from apps.ai_router.models import AIUsageLog
    start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = {r["provider"]: r for r in AIUsageLog.objects.filter(at__gte=start).values("provider").annotate(
        n=Count("id"), tin=Sum("tokens_in"), tout=Sum("tokens_out"), c=Sum("cost_usd"))}
    primary = ss.get_setting("ai.primary", "openai")
    lines = [f"<b>Asosiy provayder:</b> {primary} · <b>Zaxira:</b> {'o`chiq' if ss.get_setting('ai.fallback', 'auto') == 'none' else 'avtomatik'}"]
    for prov in ("openai", "claude"):
        n_keys = AIKey.objects.filter(provider=prov, enabled=True).count()
        r = rows.get(prov)
        txt = f"<b>{prov}:</b> kalit {'✅ ' + str(n_keys) + ' ta' if n_keys else '❌ yo`q'}"
        if r:
            txt += f" · shu oy {r['n']} so'rov, {(r['tin'] or 0) + (r['tout'] or 0):,} token, taxminiy ${(r['c'] or 0):.2f}"
        lines.append(txt)
    if not AIKey.objects.filter(enabled=True).exists():
        lines.append("<span style='color:#dc2626'><b>Diqqat:</b> hech qanday AI kaliti yo'q: pastdagi «AI kalit qo'shish» dan OpenAI yoki Claude kalitini kiriting.</span>")
    lines.append("<span class='muted'>Qoldiq mablag'ni platform.openai.com va console.anthropic.com kabinetidan ko'rasiz; bu yerda faqat tokenlardan taxminiy sarf ko'rsatiladi.</span>")
    return {"type": "html", "title": "AI holati", "html": "<br>".join(lines).replace("`", "&#x27;")}
