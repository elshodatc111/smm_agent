"""Mijoz kabineti boti (faqat Telegram; veb-kirish yo'q). Long-polling, requests orqali. Mantiq `handle_update` da (testlanadi)."""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from apps.core.notify import notify
from apps.core.settings_store import get_secret, get_setting

from .models import ClientBotUser, ClientInvite

log = logging.getLogger(__name__)


class BotAPI:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"

    def _call(self, method, **kw):
        files = kw.pop("files", None)
        r = requests.post(f"{self.base}/{method}", data=kw if files else None, json=None if files else kw, files=files, timeout=60)
        return r.json()

    def send(self, chat_id, text, buttons=None):
        kw = {"chat_id": chat_id, "text": text[:4000]}
        if buttons:
            kw["reply_markup"] = {"inline_keyboard": buttons}
        return self._call("sendMessage", **kw)

    def send_document(self, chat_id, path, caption=""):
        with open(path, "rb") as f:
            return self._call("sendDocument", chat_id=chat_id, caption=caption[:900], files={"document": f})

    def answer(self, cb_id, text=""):
        return self._call("answerCallbackQuery", callback_query_id=cb_id, text=text)


class FakeBotAPI:
    def __init__(self):
        self.sent, self.docs = [], []

    def send(self, chat_id, text, buttons=None): self.sent.append((chat_id, text, buttons))
    def send_document(self, chat_id, path, caption=""): self.docs.append((chat_id, path, caption))
    def answer(self, cb_id, text=""): pass


def make_api() -> BotAPI | None:
    from .models import ClientBotUser  # noqa: F401
    from apps.connections.models import TelegramBot
    b = TelegramBot.objects.filter(is_agency_bot=True, active=True).first()
    token = b.token() if b else get_secret("telegram.agency_bot_token")
    return BotAPI(token) if token else None


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def create_invite(business_ids: list[int], user, label: str = "", hours: int = 72) -> str:
    code = secrets.token_urlsafe(9)
    ClientInvite.objects.create(code_hash=hash_code(code), business_ids=business_ids, label=label, created_by=user,
                                expires_at=timezone.now() + timedelta(hours=hours))
    return code


def redeem(code: str, tg_user_id: int, name: str) -> ClientBotUser | None:
    inv = ClientInvite.objects.filter(code_hash=hash_code(code.strip()), used_at__isnull=True, expires_at__gt=timezone.now()).first()
    if not inv:
        return None
    inv.used_at = timezone.now()
    inv.save(update_fields=["used_at"])
    u, _ = ClientBotUser.objects.get_or_create(tg_user_id=tg_user_id)
    u.name, u.active = name, True
    u.business_ids = sorted(set(u.business_ids) | set(inv.business_ids))
    u.current_business = u.current_business if u.current_business in u.business_ids else (u.business_ids[0] if u.business_ids else None)
    u.save()
    return u


def _menu(u: ClientBotUser):
    allowed = set(u.allowed(u.current_business)) if u.current_business else set()
    rows = []
    def add(sec, text, data):
        if sec in allowed:
            rows.append([{"text": text, "callback_data": data}])
    add("kpi", "Asosiy ko'rsatkichlar", "kpi")
    add("report_weekly", "Haftalik hisobot", "rep:weekly")
    add("report_monthly", "Oylik hisobot", "rep:monthly")
    add("top_posts", "Eng yaxshi postlar", "top")
    add("content_plan", "Kontent-reja", "plan")
    add("report_issue", "Muammo haqida xabar", "issue")
    if len(u.business_ids) > 1:
        rows.append([{"text": "Biznesni almashtirish", "callback_data": "biz"}])
    return rows


def _biz(u):
    from apps.businesses.models import Business
    return Business.objects.filter(pk=u.current_business).first() if u.current_business else None


def handle_update(upd: dict, api) -> None:
    if "callback_query" in upd:
        cq = upd["callback_query"]
        _on_text_or_cb(cq["from"], cq["message"]["chat"]["id"], None, cq["data"], api, cq["id"])
    elif "message" in upd:
        m = upd["message"]
        _on_text_or_cb(m["from"], m["chat"]["id"], m.get("text", ""), None, api, None)


def _on_text_or_cb(frm, chat, text, data, api, cb_id):
    from apps.metrics import analytics as an
    uid = frm["id"]
    name = (frm.get("first_name", "") + " " + frm.get("last_name", "")).strip()
    if text and text.startswith("/start"):
        parts = text.split(maxsplit=1)
        u = ClientBotUser.objects.filter(tg_user_id=uid, active=True).first()
        if len(parts) == 2:
            u = redeem(parts[1], uid, name)
            if not u:
                api.send(chat, "Taklif kodi yaroqsiz yoki muddati tugagan. Agentlikdan yangi kod so'rang.")
                return
            api.send(chat, f"Xush kelibsiz, {name or 'mijoz'}! Siz agentlik hisobotlariga ulandingiz.")
        elif not u:
            api.send(chat, "Bu bot faqat agentlik mijozlari uchun. Taklif kodini /start KOD ko'rinishida yuboring.")
            return
        api.send(chat, "Bosh menyu:", _menu(u))
        return
    u = ClientBotUser.objects.filter(tg_user_id=uid, active=True).first()
    if not u:
        api.send(chat, "Kirish uchun agentlikdan taklif kodi oling: /start KOD")
        return
    b = _biz(u)
    if cb_id:
        api.answer(cb_id)
    # kutilayotgan matn (muammo / o'zgartirish izohi)
    if text and u.awaiting:
        aw, u.awaiting = u.awaiting, {}
        u.save(update_fields=["awaiting"])
        if aw["type"] == "issue" and b:
            notify("task.assigned", f"Mijozdan xabar: {b.name}", text[:500], business_id=b.pk, severity="warn", link="/")
            api.send(chat, "Xabaringiz agentlikka yuborildi. Rahmat!", _menu(u))
        return
    if not data:
        api.send(chat, "Menyu:", _menu(u))
        return
    if not b:
        api.send(chat, "Biznes tanlanmagan.")
        return
    allowed = set(u.allowed(b.pk))
    if data == "biz":
        from apps.businesses.models import Business
        api.send(chat, "Biznesni tanlang:", [[{"text": x.name, "callback_data": f"setbiz:{x.pk}"}] for x in Business.objects.filter(pk__in=u.business_ids)])
    elif data.startswith("setbiz:"):
        bid = int(data.split(":")[1])
        if bid in u.business_ids:
            u.current_business = bid
            u.save(update_fields=["current_business"])
            api.send(chat, "Biznes almashtirildi.", _menu(u))
    elif data == "kpi" and "kpi" in allowed:
        c = an.compare_periods(b, 30)
        k, d = c["current"], c["delta_pct"]
        f = lambda key: "" if d.get(key) is None else f" ({d[key]:+.0f}%)"
        api.send(chat, f"{b.name} — oxirgi 30 kun\nObunachilar: {k['followers']} ({k['followers_delta']:+d})\nPostlar: {k['posts']}{f('posts')}\n"
                       f"Ko'rishlar: {k['views']}{f('views')}\nER: {(k['er'] or 0):.1%}", _menu(u))
    elif data.startswith("rep:") and f"report_{data[4:]}" in allowed:
        from apps.reports.models import Report
        r = Report.objects.filter(business=b, kind=data[4:], status__in=["ready", "sent"]).order_by("-created_at").first()
        if not r:
            api.send(chat, "Hisobot hali tayyor emas. Agentlik tez orada yuboradi.", _menu(u))
        else:
            api.send(chat, r.summary_text or "Hisobot")
            if r.pdf:
                api.send_document(chat, r.pdf.path, f"{r.get_kind_display()} hisobot")
    elif data == "top" and "top_posts" in allowed:
        rows = an.top_posts(b, 5)
        api.send(chat, "Eng yaxshi postlar:\n" + "\n".join(f"{i + 1}. {(r.post.text or '')[:60]} — {r.views or 0} ko'rish, ER {(r.er or 0):.1%}" for i, r in enumerate(rows)) or "Hali ma'lumot yo'q", _menu(u))
    elif data == "plan" and "content_plan" in allowed:
        from apps.content.models import ContentItem
        items = ContentItem.objects.filter(business=b, status__in=["scheduled", "draft"], scheduled_at__gte=timezone.now()).order_by("scheduled_at")[:10]
        from apps.core.utils import fmt_dt
        api.send(chat, "Yaqin reja:\n" + ("\n".join(f"• {fmt_dt(i.scheduled_at)} — {i.title} ({i.get_status_display()})" for i in items) or "Reja bo'sh."), _menu(u))
    elif data == "issue" and "report_issue" in allowed:
        u.awaiting = {"type": "issue"}
        u.save(update_fields=["awaiting"])
        api.send(chat, "Muammoni yozib yuboring.")
    else:
        api.send(chat, "Bu bo'limga ruxsat berilmagan.", _menu(u))


def deliver_report(report, api=None) -> int:
    api = api or make_api()
    if api is None:
        raise RuntimeError("Agentlik boti tokeni kiritilmagan")
    sec = "report_weekly" if report.kind == "weekly" else "report_monthly"
    n = 0
    for u in ClientBotUser.objects.filter(active=True):
        if report.business_id in u.business_ids and sec in u.allowed(report.business_id):
            link = ""
            base = (get_setting("general.public_url", "") or "").rstrip("/")
            if base and report.data:
                import secrets
                if not report.share_token or not report.share_expires or report.share_expires < timezone.now() + timedelta(days=1):
                    report.share_token, report.share_expires = secrets.token_urlsafe(24), timezone.now() + timedelta(days=14)
                    report.save(update_fields=["share_token", "share_expires"])
                link = f"\n\n📊 Chiroyli sahifada ko'rish: {base}/h/{report.share_token}/"
            api.send(u.tg_user_id, f"{report.business.name} — {report.get_kind_display()} hisobot\n\n{report.summary_text}{link}"[:3900])
            if report.pdf:
                api.send_document(u.tg_user_id, report.pdf.path, "PDF hisobot")
            n += 1
    return n


def run_bot_loop(stop_event) -> None:
    """Worker ichidagi oqim. Token bo'lmasa har 60 soniyada qayta tekshiradi."""
    from django.db import close_old_connections
    from apps.jobs.worker import Backoff
    bo = Backoff(10.0, 300.0)
    offset = 0
    while not stop_event.is_set():
        try:
            api = make_api()
            if api is None or settings.USE_FAKES:
                stop_event.wait(60)
                continue
            r = requests.post(f"{api.base}/getUpdates", json={"offset": offset, "timeout": 25, "allowed_updates": ["message", "callback_query"]}, timeout=40).json()
            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    handle_update(upd, api)
                except Exception:  # noqa: BLE001
                    log.exception("bot handler xatosi")
            bo.ok()
        except Exception as e:  # noqa: BLE001
            stop_event.wait(bo.fail("bot loop (Telegram bilan aloqa)", e))
        finally:
            close_old_connections()
