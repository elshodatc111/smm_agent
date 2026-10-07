from __future__ import annotations

import base64
import json
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.connections import instagram, youtube
from apps.connections.base import Credentials, PlatformError
from apps.connections.models import Competitor, SocialAccount, TelegramBot, TelegramSession
from apps.connections.registry import get_connector
from apps.core import crypto
from apps.core.audit import audit
from apps.core.settings_store import get_setting
from apps.jobs.queue import enqueue
from . import ui
from .common import get_obj
from .forms import CompetitorForm, TelegramChannelForm


def _accounts(request, code):
    ids = perms.businesses_for(request.user, code).values_list("pk", flat=True)
    qs = SocialAccount.objects.filter(business_id__in=list(ids), archived_at__isnull=True).select_related("business")
    if request.business:
        qs = qs.filter(business=request.business)
    return qs


@login_required
@require_permission("connections.view")
def connection_list(request):
    rows = []
    for a in _accounts(request, "connections.view"):
        rows.append([ui.link(str(a), f"/ulanishlar/{a.pk}/"), a.business.name, ui.badge(a.get_status_display(), a.status, a.last_error[:80] or None),
                     ui.dt(a.last_collect_at), ui.dt(a.token_expires_at) if a.token_expires_at else "—"])
    tb = []
    if request.business and perms.can(request.user, "connections.create", request.business):
        tb.append({"label": "Yangi ulanish", "url": "/ulanishlar/yangi/", "cls": "primary"})
    blocks = [ui.table(None, ["Hisob", "Biznes", "Holat", "Oxirgi yig'ish", "Token muddati"], rows,
                       "Ulanish yo'q. Yuqoridan biznesni tanlab «Yangi ulanish»ni bosing.")]
    if request.user.is_admin or perms.can(request.user, "settings.configure", None):
        blocks.append(ui.table("Telegram botlar va Telethon sessiyalar (agentlik darajasida)", ["Tur", "Nomi", "Holat", ""],
                               [["Bot", b.name, ui.badge("Faol" if b.active else "O'chiq", "active" if b.active else "paused"), ""] for b in TelegramBot.objects.all()] +
                               [["Telethon", s.name, ui.badge("Faol" if s.active else "O'chiq", "active" if s.active else "paused",
                                                                 s.last_error or f"bugun {s.requests_today} so'rov"), ""] for s in TelegramSession.objects.all()]))
        tb.append({"label": "Telethon sessiyasi qo'shish", "url": "/ulanishlar/telethon/", "cls": ""})
    return ui.page(request, "Ulanishlar", blocks, toolbar=tb)


@login_required
@require_permission("connections.create")
def connection_new(request):
    b = request.business
    if not b:
        messages.info(request, "Avval yuqoridan biznesni tanlang.")
        return redirect("connection_list")
    if not perms.can(request.user, "connections.create", b):
        raise Http404
    blocks = [{"type": "html", "title": "Instagram va YouTube", "html":
               '<p>Rasmiy OAuth orqali ulanadi — hech qachon login/parol so\'ralmaydi.</p><div class="row">'
               '<a class="btn primary" href="/ulanishlar/oauth/instagram/boshlash/">Instagram ulash</a>'
               '<a class="btn primary" href="/ulanishlar/oauth/youtube/boshlash/">YouTube ulash</a></div>'
               '<p class="help">Qanday sozlash: <a href="/yoriqnoma/">Yo\'riqnoma</a> bo\'limi.</p>'}]
    form = TelegramChannelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        new_bot = None
        try:
            bot = d["bot"]
            if not bot:
                if not d["new_bot_token"]:
                    raise PlatformError("bot yo'q", user_message_uz="Botni tanlang yoki yangi bot tokenini kiriting.")
                new_bot = bot = TelegramBot(name=d["new_bot_name"] or "Bot")
                bot.set_token(d["new_bot_token"])
            acc = SocialAccount(business=b, platform="telegram", name=d["name"], handle=d["channel"].lstrip("@"), bot=bot, tg_session=d["tg_session"])
            acc.set_credentials({"chat": d["channel"]})
            if SocialAccount.objects.filter(business=b, platform="telegram", handle=acc.handle, archived_at__isnull=True).exists():
                raise PlatformError("dublikat", user_message_uz="Bu kanal shu biznesga allaqachon ulangan.")
            info = get_connector(acc).connect(Credentials({}))   # tarmoq chaqiruvi — DB tranzaksiyasidan tashqarida
            with transaction.atomic():
                if new_bot is not None:
                    new_bot.save()
                    acc.bot = new_bot
                acc.external_id, acc.status = info.external_id, "active"
                acc.handle = info.handle or acc.handle
                acc.save()
            audit("connection.create", user=request.user, business_id=b.pk, target=str(acc))
            enqueue("historical_import", {"connection_id": acc.pk}, queue="collect", business_id=b.pk)
            messages.success(request, f"Ulandi: {acc.name}. Tarixiy ma'lumot importi boshlandi.")
            return redirect("connection_detail", pk=acc.pk)
        except PlatformError as e:
            messages.error(request, e.user_message_uz or str(e))
    blocks.append(ui.form_block(form, "Telegram kanal", "Ulash va tekshirish",
                                intro="Bot kanalda <b>administrator</b> bo'lishi kerak (post yuborish, tahrirlash, o'chirish)."))
    return ui.page(request, "Yangi ulanish", blocks, subtitle=b.name)


# ---------------- OAuth ----------------
def redirect_uri(provider: str) -> str:
    """Ustuvorlik: 1) oauth.callback_url (masalan http://localhost:8000 — serverning o'zida ulanganda),
    2) Cloudflare Worker (har ikkala tarmoq uchun https), 3) PUBLIC_BASE_URL."""
    custom = (get_setting("oauth.callback_url", "") or "").rstrip("/")
    if custom:
        return f"{custom}/oauth/{provider}/done/"
    w = (get_setting("worker.cloudflare_url", "") or "").rstrip("/")
    if w:
        return f"{w}/oauth/{provider}/callback"
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/oauth/{provider}/done/"


def _state(request, provider: str) -> str:
    nonce = secrets.token_urlsafe(16)
    request.session["oauth"] = {"provider": provider, "nonce": nonce, "business": request.business.pk}
    meta = base64.urlsafe_b64encode(json.dumps({"b": settings.PUBLIC_BASE_URL.rstrip("/"), "p": provider}).encode()).decode().rstrip("=")
    return f"{meta}.{nonce}"


def _go_external(request, url: str):
    """Tashqi saytga (Meta/Google) o'tish: React (fetch) so'rovida JSON, oddiy brauzer so'rovida 302."""
    if request.headers.get("X-Requested-With") == "fetch":
        from django.http import JsonResponse
        return JsonResponse({"kind": "external", "url": url})
    return redirect(url)


@login_required
@require_permission("connections.create")
def oauth_start(request, provider):
    if provider not in ("instagram", "youtube"):
        raise Http404
    if not request.business:
        messages.info(request, "Avval yuqoridan biznesni tanlang, keyin ulang.")
        return redirect("connection_list")
    if settings.USE_FAKES:   # kalitsiz demo: haqiqiy OAuth yo'q, ulanish to'g'ridan-to'g'ri yaratiladi
        acc = SocialAccount(business=request.business, platform=provider, name=f"Demo {provider}", handle=f"demo_{provider}", external_id=f"fake-{provider}", status="active")
        acc.set_credentials({"access_token": "fake", "refresh_token": "fake"})
        acc.save()
        messages.success(request, "Demo rejim: soxta ulanish yaratildi (USE_FAKES=1).")
        return redirect("connection_detail", pk=acc.pk)
    state = _state(request, provider)
    uri = redirect_uri(provider)
    if provider == "instagram":
        if not get_setting("meta.app_id", ""):
            messages.error(request, "Avval Sozlamalar → API kalitlar bo'limida Meta App ID/Secret kiriting (Yo'riqnomaga qarang).")
            return redirect("connection_new")
        return _go_external(request, instagram.authorize_url(uri, state))
    if not get_setting("google.client_id", ""):
        messages.error(request, "Avval Sozlamalar → API kalitlar bo'limida Google Client ID/Secret kiriting.")
        return redirect("connection_new")
    return _go_external(request, youtube.authorize_url(uri, state))


@login_required
def oauth_done(request, provider):
    saved = request.session.pop("oauth", None)
    state = request.GET.get("state", "")
    if not saved or saved.get("provider") != provider or state.split(".")[-1] != saved["nonce"]:
        messages.error(request, "OAuth holati mos kelmadi (muddati o'tgan bo'lishi mumkin). Qaytadan urinib ko'ring.")
        return redirect("connection_list")
    if request.GET.get("error") or not request.GET.get("code"):
        messages.error(request, f"Ulanish bekor qilindi: {request.GET.get('error_description') or request.GET.get('error', '')}")
        return redirect("connection_list")
    from apps.businesses.models import Business
    biz = Business.objects.filter(pk=saved["business"]).first()
    if not biz or not perms.can(request.user, "connections.create", biz):
        raise Http404
    try:
        mod = instagram if provider == "instagram" else youtube
        cred = mod.exchange_code(request.GET["code"], redirect_uri(provider))
        acc = SocialAccount(business=biz, platform=provider, name="…", status="active", token_expires_at=cred.expires_at if provider == "instagram" else None, scopes=cred.scopes)
        acc.set_credentials(cred.data)
        info = get_connector(acc).connect(cred)   # tarmoq chaqiruvi saqlashdan oldin: xato bo'lsa yarim ulanish qolmaydi
        acc.external_id, acc.handle, acc.name = info.external_id, info.handle or info.external_id, info.title or info.handle or provider
        existing = SocialAccount.objects.filter(business=biz, platform=provider, external_id=acc.external_id).first()
        if existing:   # qayta ulash: yangi yozuv yaratmay tokenni yangilaymiz
            existing.set_credentials(cred.data)
            existing.token_expires_at, existing.scopes, existing.status, existing.last_error = (cred.expires_at if provider == "instagram" else None), cred.scopes, "active", ""
            existing.archived_at = None
            existing.save()
            audit("connection.reconnect", user=request.user, business_id=biz.pk, target=str(existing))
            messages.success(request, f"Qayta ulandi: {existing.name}.")
            return redirect("connection_detail", pk=existing.pk)
        acc.save()
        audit("connection.create", user=request.user, business_id=biz.pk, target=str(acc))
        enqueue("historical_import", {"connection_id": acc.pk}, queue="collect", business_id=biz.pk)
        messages.success(request, f"Ulandi: {acc.name}. Tarixiy import boshlandi.")
        return redirect("connection_detail", pk=acc.pk)
    except PlatformError as e:
        messages.error(request, e.user_message_uz or str(e))
    return redirect("connection_list")


# ---------------- Hisob sahifasi ----------------
@login_required
def connection_detail(request, pk):
    a = get_obj(request, SocialAccount, pk, "connections.view")
    rows = [[k, v] for k, v in [("Platforma", a.get_platform_display()), ("Handle", a.handle), ("ID", a.external_id), ("Holat", a.get_status_display()),
                                ("Token muddati", ui.dt(a.token_expires_at) if a.token_expires_at else "—"), ("Ruxsatlar", ", ".join(a.scopes) or "—"),
                                ("Oxirgi yig'ish", ui.dt(a.last_collect_at)), ("Avto-nashr", "Yoqiq" if a.autopublish_enabled else "O'chiq"),
                                ("Tarixiy import", "Bajarildi" if a.history_imported else "Kutilmoqda"), ("Xato", a.last_error or "—")]]
    blocks = [ui.kv("Ma'lumot", rows)]
    base = f"/ulanishlar/{a.pk}"
    acts = [ui.btn("Ulanishni tekshirish", f"{base}/test/", "primary"), ui.btn("Hozir ma'lumot yig'ish", f"{base}/yigish/"),
            ui.btn("Avto-nashrni " + ("o'chirish" if a.autopublish_enabled else "yoqish"), f"{base}/killswitch/"),
            ui.btn("To'xtatish" if a.status != "paused" else "Davom ettirish", f"{base}/pauza/"),
            ui.btn("Arxivlash", f"{base}/arxiv/", "danger", "Ulanish arxivlanadi (ma'lumotlar saqlanadi). Davom etasizmi?")]
    if a.platform in ("instagram", "youtube"):
        acts.append(ui.btn("Qayta ulash (OAuth)", f"/ulanishlar/oauth/{a.platform}/boshlash/"))
    blocks.append({"type": "actions", "title": "Amallar", "buttons": [x if "post" in x else x for x in acts]})
    return ui.page(request, str(a), blocks, subtitle=a.business.name, toolbar=[{"label": "Orqaga", "url": "/ulanishlar/"}])


def _act(request, pk, code="connections.edit"):
    return get_obj(request, SocialAccount, pk, code)


@login_required
@require_POST
def connection_test(request, pk):
    a = _act(request, pk)
    try:
        r = get_connector(a).health_check()
    except Exception as e:  # noqa: BLE001
        r = None
        messages.error(request, getattr(e, "user_message_uz", None) or str(e))
    if r:
        (messages.success if r.ok else messages.error)(request, r.message_uz)
        a.status = "active" if r.ok else "error"
        a.last_error = "" if r.ok else r.message_uz[:400]
        a.save(update_fields=["status", "last_error"])
    return redirect("connection_detail", pk=a.pk)


@login_required
@require_POST
def connection_collect(request, pk):
    a = _act(request, pk)
    enqueue("collect_account", {"connection_id": a.pk}, queue="collect", business_id=a.business_id, dedupe_key=f"collect:{a.pk}:manual", priority=3)
    messages.success(request, "Yig'ish navbatga qo'yildi.")
    return redirect("connection_detail", pk=a.pk)


@login_required
@require_POST
def connection_killswitch(request, pk):
    a = _act(request, pk, "publish.publish")
    a.autopublish_enabled = not a.autopublish_enabled
    a.save(update_fields=["autopublish_enabled"])
    audit("connection.killswitch", user=request.user, business_id=a.business_id, target=str(a), detail={"enabled": a.autopublish_enabled})
    return redirect("connection_detail", pk=a.pk)


@login_required
@require_POST
def connection_pause(request, pk):
    a = _act(request, pk)
    a.status = "active" if a.status == "paused" else "paused"
    a.save(update_fields=["status"])
    return redirect("connection_detail", pk=a.pk)


@login_required
@require_POST
def connection_archive(request, pk):
    a = _act(request, pk, "connections.delete")
    a.archived_at, a.status = timezone.now(), "archived"
    a.save(update_fields=["archived_at", "status"])
    audit("connection.archive", user=request.user, business_id=a.business_id, target=str(a))
    return redirect("connection_list")


# ---------------- Telethon sessiyasi ----------------
@login_required
@require_permission("settings.configure")
def telethon_login(request):
    from apps.connections import telethon_login as tl
    st = request.session.get("tl", {})
    step = "phone" if not st else ("password" if st.get("need_password") else "code")
    if request.method == "POST":
        try:
            if settings.USE_FAKES:
                s = TelegramSession(name=request.POST.get("name") or "Demo", phone=request.POST.get("phone", "+998"), session_enc=crypto.encrypt("fake"))
                s.save()
                messages.success(request, "Demo Telethon sessiyasi yaratildi.")
                return redirect("connection_list")
            if step == "phone":
                r = tl.send_code(request.POST["phone"].strip())
                request.session["tl"] = {**r, "phone": request.POST["phone"].strip(), "name": request.POST.get("name") or "Telethon"}
                messages.info(request, "Kod Telegram ilovasiga yuborildi.")
            else:
                r = tl.sign_in(st["phone"], st["session"], st["hash"], code=request.POST.get("code", "").strip(), password=request.POST.get("password", ""))
                if r.get("need_password"):
                    request.session["tl"] = {**st, "session": r["session"], "need_password": True}
                    messages.info(request, "Ikki bosqichli parol kerak.")
                else:
                    TelegramSession.objects.create(name=st["name"], phone=st["phone"], session_enc=crypto.encrypt(r["session"]))
                    request.session.pop("tl", None)
                    audit("telethon.session_added", user=request.user, target=st["name"])
                    messages.success(request, "Telethon sessiyasi saqlandi (faqat o'qish rejimida ishlaydi).")
                    return redirect("connection_list")
        except PlatformError as e:
            messages.error(request, e.user_message_uz or str(e))
        except Exception as e:  # noqa: BLE001
            request.session.pop("tl", None)
            messages.error(request, f"Kirishda xato: {e}")
        return redirect("telethon_login")
    fields = {"phone": '<label>Ism (belgi)</label><input name="name" value="Telethon-1"><label>Telefon (+998…)</label><input name="phone" required>',
              "code": '<label>Telegramga kelgan kod</label><input name="code" required autofocus>',
              "password": '<label>2 bosqichli parol</label><input type="password" name="password" required>'}[step]
    html = f'<form method="post">{{csrf}}{fields}<div class="mt"><button class="btn primary">Davom etish</button></div></form>'
    from django.middleware.csrf import get_token
    html = html.replace("{csrf}", f'<input type="hidden" name="csrfmiddlewaretoken" value="{get_token(request)}">')
    intro = ("<b>Ajratilgan SIM/raqam ishlating</b> — asosiy raqamingizni emas. Sessiya faqat o'qish uchun ishlaydi, kunlik limit va kutish vaqtlari bilan himoyalangan. "
             "Telegram API ID/Hash Sozlamalarda kiritilgan bo'lishi kerak.")
    return ui.page(request, "Telethon sessiyasi qo'shish", [{"type": "html", "title": None, "html": f"<p class='muted'>{intro}</p>{html}"}])


# ---------------- Raqobatchilar ----------------
@login_required
@require_permission("competitors.view")
def competitor_list(request):
    b = request.business
    ids = [b.pk] if b else list(perms.businesses_for(request.user, "competitors.view").values_list("pk", flat=True))
    qs = Competitor.objects.filter(business_id__in=ids).select_related("business")
    rows = []
    for c in qs:
        last = c.metrics.order_by("-taken_at").first() if hasattr(c, "metrics") else None
        rows.append([ui.link(c.name or c.handle, f"/raqobatchilar/{c.pk}/"), c.get_platform_display(), c.business.name, last.followers if last else "—",
                     ui.dt(c.last_light_at), ui.badge("Faol" if c.active else "O'chiq", "active" if c.active else "paused")])
    blocks = []
    from apps.core.settings_store import get_setting as _gs
    if qs.exists() and not (_gs("scrapecreators.api_key", "") or _gs("youtube.api_key", "")):
        blocks.append({"type": "text", "title": "Ma'lumot provayderi hali ulanmagan",
                       "text": "Raqobatchilarni qo'shib qo'yishingiz mumkin — ular saqlanadi. Obuna/to'lov talab qiladigan ma'lumot provayderi (ScrapeCreators va boshqalar) loyiha ishga tushganda ulanadi; "
                               "shundan so'ng raqobatchi postlari, tahlil va g'oyalar avtomatik to'la ishlaydi. Hozircha hech qanday to'lov qilish shart emas — g'oyalar bankida o'z natijalaringiz asosidagi g'oyalar chiqaveradi."})
    if b and qs.exists():
        from apps.ai_router.models import AIGeneration
        g = AIGeneration.objects.filter(business=b, kind="competitor_summary").exclude(data=None).order_by("-created_at").first()
        if g:
            d = g.data or {}
            blocks.append({"type": "text", "title": f"AI xulosa ({ui.dt(g.created_at)})", "text": d.get("summary", "")})
            comp_rows = [[x.get("name"), x.get("strength"), x.get("weakness")] for x in d.get("competitors", []) if isinstance(x, dict)]
            if comp_rows:
                blocks.append(ui.table("Raqobatchilar: kuchli va zaif tomonlari", ["Raqobatchi", "Kuchli tomoni", "Zaif tomoni"], comp_rows))
            for t, k in (("Biz foydalana oladigan bo'shliqlar", "gaps"), ("Bu hafta qilinadigan ishlar", "actions"), ("Kuzatib borish kerak", "watch")):
                items = [str(i) for i in d.get(k, []) if i]
                if items:
                    blocks.append({"type": "text", "title": t, "text": "\n".join("• " + i for i in items)})
        if perms.can(request.user, "competitors.view", b):
            blocks.append({"type": "actions", "title": "AI tahlil", "buttons": [ui.btn("Raqobatchilar bo'yicha AI xulosa olish", "/raqobatchilar/xulosa/", "primary")]})
    blocks.append(ui.table("Kuzatilayotganlar", ["Nomi", "Tarmoq", "Biznes", "Obunachi", "Oxirgi tekshiruv", "Holat"], rows, "Raqobatchi qo'shilmagan."))
    if b and perms.can(request.user, "competitors.create", b):
        blocks.append(ui.form_block(CompetitorForm(), "Raqobatchi qo'shish", "Qo'shish", action="/raqobatchilar/qoshish/"))
    return ui.page(request, "Raqobatchilar", blocks)


@login_required
@require_POST
def competitor_summary(request):
    from apps.studio import services as st
    b = request.business
    if not b or not perms.can(request.user, "competitors.view", b):
        raise Http404
    try:
        st.competitor_summary(b, request.user)
        messages.success(request, "AI xulosa tayyor.")
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:  # noqa: BLE001
        messages.error(request, getattr(e, "user_message_uz", None) or f"AI xatosi: {e}")
    return redirect("competitor_list")


@login_required
@require_POST
def competitor_add(request):
    b = request.business
    if not b or not perms.can(request.user, "competitors.create", b):
        raise Http404
    f = CompetitorForm(request.POST)
    if f.is_valid():
        c = f.save(commit=False)
        c.business = b
        c.handle = c.handle.lstrip("@").strip()
        c.save()
        enqueue("collect_competitor", {"competitor_id": c.pk, "depth": "light"}, queue="collect", business_id=b.pk, dedupe_key=f"comp:{c.pk}:first")
        audit("competitor.add", user=request.user, business_id=b.pk, target=f"competitor:{c.pk}", detail={"handle": c.handle})
        messages.success(request, "Raqobatchi qo'shildi, birinchi tekshiruv navbatda.")
    else:
        messages.error(request, "Maydonlarni tekshiring (bunday raqobatchi allaqachon bo'lishi mumkin).")
    return redirect("competitor_list")


@login_required
def competitor_detail(request, pk):
    c = get_obj(request, Competitor, pk, "competitors.view")
    ms = list(c.metrics.order_by("taken_at")[:90])
    charts = [{"id": "cf", "kind": "line", "labels": [m.taken_at.strftime("%d.%m") for m in ms], "series": [{"name": "Obunachi", "data": [m.followers or 0 for m in ms]}]}] if len(ms) > 1 else []
    posts = c.posts.order_by("-published_at")[:15]
    blocks = [ui.kv("Ma'lumot", [("Tarmoq", c.get_platform_display()), ("Handle", c.handle), ("Izoh", c.note), ("Oxirgi yengil tekshiruv", ui.dt(c.last_light_at)), ("Oxirgi to'liq", ui.dt(c.last_full_at))])]
    if charts:
        blocks.append({"type": "chart", "title": "Obunachilar dinamikasi", "id": "cf"})
    blocks.append(ui.table("So'nggi postlar", ["Sana", "Matn", "Ko'rish", "Layk", "Izoh"], [[ui.dt(p.published_at), (p.text or "")[:90], p.views or "—", p.likes or "—", p.comments or "—"] for p in posts]))
    acts = [ui.btn("Hozir tekshirish", f"/raqobatchilar/{c.pk}/tekshir/", "primary"), ui.btn("O'chirish", f"/raqobatchilar/{c.pk}/ochir/", "danger", "Raqobatchi o'chirilsinmi?")]
    blocks.append({"type": "actions", "title": "Amallar", "buttons": acts})
    return ui.page(request, c.name or c.handle, blocks, charts=charts, toolbar=[{"label": "Orqaga", "url": "/raqobatchilar/"}])


@login_required
@require_POST
def competitor_check(request, pk):
    c = get_obj(request, Competitor, pk, "competitors.edit")
    enqueue("collect_competitor", {"competitor_id": c.pk, "depth": "light"}, queue="collect", business_id=c.business_id, dedupe_key=f"comp:{c.pk}:manual")
    messages.success(request, "Tekshiruv navbatga qo'yildi.")
    return redirect("competitor_detail", pk=c.pk)


@login_required
@require_POST
def competitor_delete(request, pk):
    c = get_obj(request, Competitor, pk, "competitors.delete")
    audit("competitor.delete", user=request.user, business_id=c.business_id, target=f"competitor:{c.pk}", detail={"handle": c.handle})
    c.delete()
    return redirect("competitor_list")
