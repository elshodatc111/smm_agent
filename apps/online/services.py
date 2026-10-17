"""Onlayn kanal xizmatlari: lead, to'lov, obuna, guruh nazorati, statistika, botni sozlash."""
from __future__ import annotations

import html
import logging
import re
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core.utils import UZ_MONTHS, fmt_dt, local

from . import defaults as D
from .models import (BotEvent, Lead, OnlineMedia, OnlineProject, Payment, ProjectGroup, Subscription, Tariff)
from .tgapi import TgError, get_api

log = logging.getLogger(__name__)
esc = html.escape


def fmt_d(dt) -> str:
    d = local(dt)
    return f"{d.day} {UZ_MONTHS[d.month]} {d.year}" if d else "—"


def event(project, kind, text, lead=None):
    BotEvent.objects.create(project=project, lead=lead, kind=kind[:24], text=str(text)[:300])


# ───────────────────────── lead ─────────────────────────
def upsert_lead(project, frm: dict, source: str = "", api=None) -> tuple[Lead, bool]:
    now = timezone.now()
    lead, created = Lead.objects.get_or_create(project=project, tg_id=frm["id"], defaults={
        "first_name": (frm.get("first_name") or "")[:120], "last_name": (frm.get("last_name") or "")[:120], "username": (frm.get("username") or "")[:80],
        "language": (frm.get("language_code") or "")[:10], "is_premium": bool(frm.get("is_premium")), "source": source[:80], "last_seen": now})
    if not created:
        lead.first_name = (frm.get("first_name") or lead.first_name)[:120]
        lead.last_name = (frm.get("last_name") or "")[:120]
        lead.username = (frm.get("username") or "")[:80]
        lead.language = (frm.get("language_code") or lead.language)[:10]
        lead.is_premium = bool(frm.get("is_premium"))
        lead.last_seen = now
        lead.bot_blocked = False
        if source and not lead.source:
            lead.source = source[:80]
    lead.save()
    if created:
        event(project, "lead_new", f"Yangi lead: {lead.full_name}" + (f" (manba: {source})" if source else ""), lead)
        _fill_profile(api, lead)
    return lead, created


def _fill_profile(api, lead: Lead) -> None:
    """Bio va profil rasmini olishga urinadi (Telegram bersa)."""
    if not api:
        return
    try:
        ch = api.get_chat(lead.tg_id)
        lead.bio = (ch.get("bio") or "")[:300]
    except Exception:  # noqa: BLE001
        pass
    try:
        ph = api.user_photos(lead.tg_id)
        if ph.get("total_count"):
            lead.photo_file_id = ph["photos"][0][-1]["file_id"]
    except Exception:  # noqa: BLE001
        pass
    lead.save(update_fields=["bio", "photo_file_id"])


def norm_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    if len(d) == 9:
        d = "998" + d
    return "+" + d if d else ""


def set_phone(project, lead: Lead, phone: str, api=None) -> str | None:
    lead.phone = norm_phone(phone)
    lead.phone_at = timezone.now()
    if lead.status == "new":
        lead.status = "phone"
    lead.save(update_fields=["phone", "phone_at", "status"])
    event(project, "phone", f"{lead.full_name}: telefon raqami olindi", lead)
    if api:
        _fill_profile(api, lead)
    return post_lead(project, api, lead, activity=True) if api else None


def lead_card(lead: Lead, returned: bool = False) -> str:
    head = "🔁 <b>Qaytgan lead</b>" if returned else "🆕 <b>Yangi lead</b>"
    uname = f"@{esc(lead.username)}" if lead.username else "—"
    lines = [head, "", f"👤 <b>{esc(lead.full_name)}</b>", f"📱 Telefon: <code>{esc(lead.phone or '—')}</code>", f"🔗 Username: {uname}",
             f"🆔 Telegram ID: <a href=\"tg://user?id={lead.tg_id}\">{lead.tg_id}</a>"]
    if lead.language:
        lines.append(f"🌐 Til: {esc(lead.language)}")
    if lead.is_premium:
        lines.append("⭐ Telegram Premium")
    if lead.bio:
        lines.append(f"📝 Bio: {esc(lead.bio)}")
    lines.append(f"📍 Manba: {esc(lead.source or 'to‘g‘ridan-to‘g‘ri')}")
    lines.append(f"🕒 Birinchi kirish: {fmt_dt(lead.first_seen)}")
    lines.append(f"📊 Holat: {lead.get_status_display()}")
    if lead.starts > 1:
        lines.append(f"🔄 /start bosilgan: {lead.starts} marta")
    return "\n".join(lines)


def post_lead(project, api, lead: Lead, activity: bool = False) -> str | None:
    """Leadni leadlar guruhiga bitta post qilib yuboradi.
    Qoida: telefon bo'lishi shart. Bir marta yuborilgan bo'lsa repost_days ichida takror yuborilmaydi (mavjud post yangilanadi);
    shu muddat o'tib qaytib kelsa — «Qaytgan lead» sifatida yangi post."""
    if not (api and project.leads_chat_id and lead.phone):
        return None
    now = timezone.now()
    window = timedelta(days=project.repost_days or 30)
    try:
        if lead.posted_at is None or (activity and now - lead.posted_at >= window):
            returned = lead.posted_at is not None
            text = lead_card(lead, returned)
            if lead.photo_file_id:
                m = api.send_media(project.leads_chat_id, "photo", lead.photo_file_id, caption=text)
            else:
                m = api.send(project.leads_chat_id, text)
            lead.post_msg_id, lead.posted_at = m["message_id"], now
            lead.post_count += 1
            lead.save(update_fields=["post_msg_id", "posted_at", "post_count"])
            event(project, "lead_post", f"{lead.full_name}: leadlar guruhiga {'qayta ' if returned else ''}yuborildi", lead)
            return "returned" if returned else "new"
        if lead.post_msg_id:
            text = lead_card(lead, lead.post_count > 1)
            try:
                api.edit_text(project.leads_chat_id, lead.post_msg_id, text)
            except TgError:
                api.edit_caption(project.leads_chat_id, lead.post_msg_id, text)
            return "updated"
    except TgError as e:
        project.last_error = f"Leadlar guruhi: {e.description}"[:300]
        project.save(update_fields=["last_error"])
        event(project, "error", f"Leadni guruhga yuborib bo'lmadi: {e.description}", lead)
    return None


def set_lead_status(project, api, lead: Lead, status: str) -> None:
    lead.status = status
    lead.save(update_fields=["status"])
    if lead.post_msg_id and api:
        post_lead(project, api, lead)


# ───────────────────────── obuna ─────────────────────────
def active_sub(lead: Lead) -> Subscription | None:
    return lead.subs.filter(status="active", ends_at__gt=timezone.now()).order_by("-ends_at").first()


def is_staff(project, tg_id: int) -> bool:
    return project.admins.filter(tg_id=tg_id).exists()


def has_access(project, lead: Lead | None, tg_id: int) -> bool:
    if is_staff(project, tg_id):
        return True
    if lead is None:
        return False
    return bool(lead.exempt or active_sub(lead))


def grant_subscription(project, lead: Lead, days: int, tariff: Tariff | None = None, source: str = "payment") -> Subscription:
    now = timezone.now()
    cur = active_sub(lead)
    if cur:
        cur.ends_at = cur.ends_at + timedelta(days=days)
        cur.reminded = []
        if tariff:
            cur.tariff = tariff
        cur.save(update_fields=["ends_at", "reminded", "tariff"])
        sub = cur
    else:
        sub = Subscription.objects.create(project=project, lead=lead, tariff=tariff, starts_at=now, ends_at=now + timedelta(days=days), source=source)
    event(project, "sub_grant", f"{lead.full_name}: obuna {fmt_dt(sub.ends_at)} gacha ({days} kun, {source})", lead)
    return sub


def cancel_subscription(project, api, lead: Lead, kick: bool = True) -> int:
    n = 0
    for s in lead.subs.filter(status="active"):
        s.status, s.removed_at = "cancelled", timezone.now()
        s.save(update_fields=["status", "removed_at"])
        n += 1
    event(project, "sub_cancel", f"{lead.full_name}: obuna bekor qilindi", lead)
    if kick and api and not (lead.exempt or is_staff(project, lead.tg_id)):
        remove_from_groups(project, api, lead)
    return n


def remove_from_groups(project, api, lead: Lead) -> int:
    n = 0
    for g in project.groups.all():
        try:
            st = api.get_member(g.chat_id, lead.tg_id).get("status")
            if st in ("member", "restricted"):
                api.kick(g.chat_id, lead.tg_id)
                n += 1
        except TgError as e:
            log.warning("kick xatosi %s: %s", g.chat_id, e)
    return n


def invite_links(project, api, lead: Lead) -> list[tuple[str, str]]:
    out = []
    for g in project.groups.all():
        try:
            r = api.create_invite(g.chat_id, name=f"{lead.tg_id}", expire=int((timezone.now() + timedelta(days=3)).timestamp()))
            out.append((g.title or str(g.chat_id), r["invite_link"]))
        except TgError as e:
            event(project, "error", f"Havola yaratib bo'lmadi ({g.title or g.chat_id}): {e.description}", lead)
    return out


def user_vals(project, lead: Lead, tariff: Tariff | None = None, sub: Subscription | None = None, **kw):
    sub = sub or (active_sub(lead) if lead.pk else None)
    left = max(0, int(-(-(sub.ends_at - timezone.now()).total_seconds() // 86400))) if sub else 0
    vals = dict(name=esc(lead.first_name or lead.full_name), bot=project.bot_username, project=esc(project.name),
                tariff=esc(tariff.name) if tariff else "", price=D.money(tariff.price) if tariff else "", days=tariff.days if tariff else "",
                card=esc(D.card_fmt(project.card_number)), holder=esc(project.card_holder), bank=esc(project.card_bank),
                end=fmt_d(sub.ends_at) if sub else "", left=left)
    vals.update(kw)
    return vals


# ───────────────────────── to'lov ─────────────────────────
def create_payment(project, api, lead: Lead, tariff: Tariff, file_id: str, uid: str) -> Payment:
    dup = bool(uid) and Payment.objects.filter(project=project, receipt_uid=uid).exists()
    p = Payment.objects.create(project=project, lead=lead, tariff=tariff, amount=tariff.price, receipt_file_id=file_id, receipt_uid=uid, duplicate=dup)
    lead.status = "waiting"
    lead.save(update_fields=["status"])
    event(project, "pay_new", f"{lead.full_name}: chek yubordi ({tariff.name}, {D.money(tariff.price)} so'm)" + (" ⚠ takror chek" if dup else ""), lead)
    notify_admins(project, api, p)
    return p


def payment_caption(p: Payment, status_line: str = "") -> str:
    lead = p.lead
    t = [f"💳 <b>To'lov #{p.pk}</b>" + (" — ⚠️ <b>TAKROR CHEK!</b>" if p.duplicate else ""), "",
         f"👤 {esc(lead.full_name)} ({'@' + esc(lead.username) if lead.username else lead.tg_id})", f"📱 {esc(lead.phone or '—')}",
         f"📦 Tarif: {esc(p.tariff.name) if p.tariff else '—'} ({p.tariff.days if p.tariff else '?'} kun)", f"💰 Summa: <b>{D.money(p.amount)} so'm</b>",
         f"🕒 {fmt_dt(p.created_at)}"]
    if p.duplicate:
        t.append("Bu chek rasmi oldin ham yuborilgan. Diqqat bilan tekshiring.")
    if status_line:
        t += ["", status_line]
    return "\n".join(t)


def _pay_buttons(p: Payment):
    return {"inline_keyboard": [[{"text": "✅ Tasdiqlash", "callback_data": f"pok:{p.pk}"}, {"text": "❌ Rad etish", "callback_data": f"pno:{p.pk}"}]]}


def notify_admins(project, api, p: Payment, escalation: bool = False) -> int:
    admins = list(project.admins.all())
    if not admins:
        event(project, "error", f"To'lov #{p.pk}: mas'ul admin biriktirilmagan!", p.lead)
        return 0
    prim = [a for a in admins if a.is_primary] or admins
    targets = prim if not escalation else ([a for a in admins if not a.is_primary] or prim)
    n = 0
    for a in targets:
        try:
            text = payment_caption(p, "⏰ <i>Eslatma: hali tasdiqlanmagan</i>" if escalation else "")
            if p.receipt_file_id:
                m = api.send_media(a.tg_id, "photo", p.receipt_file_id, caption=text, markup=_pay_buttons(p))
            else:
                m = api.send(a.tg_id, text, markup=_pay_buttons(p))
            p.admin_msgs = [*p.admin_msgs, [a.tg_id, m["message_id"]]]
            n += 1
        except TgError as e:
            event(project, "error", f"Adminga ({a.name or a.tg_id}) yuborib bo'lmadi: {e.description}", p.lead)
    p.save(update_fields=["admin_msgs"])
    return n


def escalate_pending(project, api) -> int:
    cutoff = timezone.now() - timedelta(minutes=project.escalate_min or 15)
    n = 0
    for p in project.payments.filter(status="pending", escalated=False, created_at__lte=cutoff).select_related("lead", "tariff"):
        p.escalated = True
        p.save(update_fields=["escalated"])
        notify_admins(project, api, p, escalation=True)
        n += 1
    return n


def decide_payment(project, api, payment_id: int, approve: bool, by: str, reason: str = "") -> tuple[bool, str]:
    """Tasdiqlash/rad etish (paneldan ham, botdan ham). Takror qaror berilmaydi."""
    with transaction.atomic():
        p = Payment.objects.select_for_update().select_related("lead", "tariff").filter(pk=payment_id, project=project).first()
        if not p:
            return False, "To'lov topilmadi."
        if p.status != "pending":
            return False, f"Bu to'lov allaqachon {p.get_status_display().lower()} ({p.decided_by})."
        p.status = "approved" if approve else "rejected"
        p.decided_by, p.decided_at = by[:80], timezone.now()
        if not approve:
            p.reject_reason = reason[:300]
        p.save()
    lead = p.lead
    if approve:
        days = p.tariff.days if p.tariff else 30
        sub = grant_subscription(project, lead, days, p.tariff, "payment")
        p.subscription = sub
        p.save(update_fields=["subscription"])
        lead.status = "sold"
        lead.save(update_fields=["status"])
        event(project, "pay_ok", f"To'lov #{p.pk} tasdiqlandi ({by}): {lead.full_name}, {D.money(p.amount)} so'm", lead)
        _tell_approved(project, api, lead, p, sub)
        archive_payment(project, api, p, by)
    else:
        lead.status = "interested"
        lead.save(update_fields=["status"])
        event(project, "pay_no", f"To'lov #{p.pk} rad etildi ({by}): {reason}", lead)
        _send_user(api, lead, D.fmt(D.get_flow(project)["texts"]["rejected"], **user_vals(project, lead, p.tariff, reason=esc(reason or "ko'rsatilmagan"))))
    _close_admin_msgs(api, p, "✅ Tasdiqlandi" if approve else "❌ Rad etildi", by)
    if lead.post_msg_id:
        post_lead(project, api, lead)
    return True, "Tasdiqlandi" if approve else "Rad etildi"


def _send_user(api, lead, text, markup=None):
    try:
        return api.send(lead.tg_id, text, markup=markup)
    except TgError as e:
        if e.blocked:
            lead.bot_blocked = True
            lead.save(update_fields=["bot_blocked"])
        return None


def _tell_approved(project, api, lead, p, sub):
    links = invite_links(project, api, lead)
    texts = D.get_flow(project)["texts"]
    text = D.fmt(texts["approved"], **user_vals(project, lead, p.tariff, sub))
    markup = {"inline_keyboard": [[{"text": f"➡️ {t}", "url": u}] for t, u in links]} if links else None
    if not links:
        text += "\n\n" + texts["no_groups"]
    _send_user(api, lead, text, markup)


def _close_admin_msgs(api, p: Payment, label: str, by: str) -> None:
    for chat, mid in p.admin_msgs:
        try:
            cap = payment_caption(p, f"{label} — {esc(by)}")
            try:
                api.edit_caption(chat, mid, cap)
            except TgError:
                api.edit_text(chat, mid, cap)
            api.edit_markup(chat, mid)
        except TgError:
            pass


def archive_payment(project, api, p: Payment, by: str) -> None:
    chat = project.pay_target
    if not (chat and api):
        return
    lead, sub = p.lead, p.subscription
    cap = (f"✅ <b>To'lov tasdiqlandi #{p.pk}</b>\n\n👤 {esc(lead.full_name)}" + (f" (@{esc(lead.username)})" if lead.username else "") +
           f"\n📱 {esc(lead.phone or '—')}\n🆔 {lead.tg_id}\n📦 {esc(p.tariff.name) if p.tariff else '—'}\n💰 {D.money(p.amount)} so'm\n"
           f"⏳ Obuna: {fmt_d(sub.ends_at) if sub else '—'} gacha\n🕒 {fmt_dt(p.decided_at)}\n👮 Tasdiqladi: {esc(by)}")
    try:
        if p.receipt_file_id:
            m = api.send_media(chat, "photo", p.receipt_file_id, caption=cap)
        else:
            m = api.send(chat, cap)
        p.archive_msg_id = m["message_id"]
        p.save(update_fields=["archive_msg_id"])
    except TgError as e:
        event(project, "error", f"To'lov arxiviga yuborib bo'lmadi: {e.description}", lead)


# ───────────────────────── muddat nazorati ─────────────────────────
def expire_subscriptions(project, api) -> int:
    now = timezone.now()
    n = 0
    for s in project.subs.filter(status="active", ends_at__lte=now).select_related("lead"):
        s.status, s.removed_at = "expired", now
        s.save(update_fields=["status", "removed_at"])
        lead = s.lead
        if active_sub(lead):
            continue
        n += 1
        event(project, "sub_end", f"{lead.full_name}: obuna muddati tugadi", lead)
        if lead.exempt or is_staff(project, lead.tg_id):
            continue
        k = remove_from_groups(project, api, lead)
        if lead.status == "sold":
            lead.status = "interested"
            lead.save(update_fields=["status"])
        _send_user(api, lead, D.fmt(D.get_flow(project)["texts"]["expired"], **user_vals(project, lead)))
        if k:
            event(project, "kick", f"{lead.full_name}: {k} ta guruhdan chiqarildi", lead)
    return n


def send_reminders(project, api) -> int:
    try:
        days = sorted({int(x) for x in project.remind_days.split(",") if x.strip().isdigit()}, reverse=True)
    except ValueError:
        days = []
    if not days:
        return 0
    now, n = timezone.now(), 0
    for s in project.subs.filter(status="active", ends_at__gt=now, ends_at__lte=now + timedelta(days=days[0] + 1)).select_related("lead", "tariff"):
        left = -(-(s.ends_at - now).total_seconds() // 86400)
        due = [d for d in days if left <= d and d not in s.reminded]
        if not due:
            continue
        s.reminded = sorted({*s.reminded, *[d for d in days if d >= left]})
        s.save(update_fields=["reminded"])
        if _send_user(api, s.lead, D.fmt(D.get_flow(project)["texts"]["expiring"], **user_vals(project, s.lead, s.tariff, s, left=int(left)))):
            n += 1
    return n


def maintenance(project, api) -> dict:
    return {"expired": expire_subscriptions(project, api), "reminders": send_reminders(project, api), "escalated": escalate_pending(project, api)}


# ───────────────────────── statistika ─────────────────────────
def stats(project, days: int | None = None) -> dict:
    now = timezone.now()
    since = now - timedelta(days=days) if days else None
    leads = project.leads.all()
    pays = project.payments.filter(status="approved")
    if since:
        leads = leads.filter(first_seen__gte=since)
        pays = pays.filter(decided_at__gte=since)
    n_leads = leads.count()
    n_phone = leads.exclude(phone="").count()
    sold = pays.count()
    buyers = pays.values("lead").distinct().count()
    rev = pays.aggregate(s=Sum("amount"))["s"] or 0
    return {"leads": n_leads, "phones": n_phone, "sales": sold, "buyers": buyers, "revenue": rev,
            "conv": round(buyers * 100 / n_leads, 1) if n_leads else 0.0,
            "pending": project.payments.filter(status="pending").count(),
            "active_subs": project.subs.filter(status="active", ends_at__gt=now).values("lead").distinct().count(),
            "expiring": project.subs.filter(status="active", ends_at__gt=now, ends_at__lte=now + timedelta(days=7)).count(),
            "rejected": project.payments.filter(status="rejected").count()}


def stats_text(project) -> str:
    out = [f"📊 <b>{esc(project.name)}: statistika</b>"]
    for label, d in (("Bugun", 1), ("7 kun", 7), ("30 kun", 30), ("Hammasi", None)):
        s = stats(project, d)
        out.append(f"\n<b>{label}</b>\n👥 Lead: {s['leads']} (telefon: {s['phones']})\n💰 Sotuv: {s['sales']} ta, {D.money(s['revenue'])} so'm\n🎯 Konversiya: {s['conv']}%")
    s = stats(project)
    out.append(f"\n✅ Faol obuna: {s['active_subs']}\n⏰ 7 kunda tugaydi: {s['expiring']}\n⏳ Kutilayotgan to'lov: {s['pending']}")
    return "\n".join(out)


def daily_series(project, days: int = 30) -> list[dict]:
    from django.db.models.functions import TruncDate
    since = timezone.now() - timedelta(days=days - 1)
    l = {r["d"]: r["n"] for r in project.leads.filter(first_seen__gte=since).annotate(d=TruncDate("first_seen")).values("d").annotate(n=Count("id"))}
    s = {r["d"]: (r["n"], r["a"] or 0) for r in project.payments.filter(status="approved", decided_at__gte=since).annotate(d=TruncDate("decided_at")).values("d").annotate(n=Count("id"), a=Sum("amount"))}
    out = []
    for i in range(days):
        d = (since + timedelta(days=i)).date()
        out.append({"d": d, "leads": l.get(d, 0), "sales": s.get(d, (0, 0))[0], "revenue": s.get(d, (0, 0))[1]})
    return out


# ───────────────────────── guruhlar va botni sozlash ─────────────────────────
def check_group(project, api, g: ProjectGroup) -> bool:
    g.checked_at = timezone.now()
    try:
        ch = api.get_chat(g.chat_id)
        g.title = (ch.get("title") or g.title)[:120]
        m = api.get_member(g.chat_id, project.bot_id or api.get_me()["id"])
        if m.get("status") == "creator":
            g.ok, g.note = True, "Tayyor"
        elif m.get("status") != "administrator":
            g.ok, g.note = False, "Bot guruhda admin emas. Botni administrator qiling."
        else:
            miss = [lbl for k, lbl in (("can_restrict_members", "a'zolarni chiqarish"), ("can_invite_users", "havola yaratish")) if not m.get(k)]
            g.ok, g.note = (not miss), ("Tayyor" if not miss else "Botga ruxsat yetishmaydi: " + ", ".join(miss))
    except TgError as e:
        g.ok, g.note = False, f"Guruhga kirib bo'lmadi: {e.description}"[:200]
    g.save()
    return g.ok


def check_post_chat(api, chat_id, bot_id) -> tuple[bool, str, str]:
    try:
        ch = api.get_chat(chat_id)
        m = api.get_member(chat_id, bot_id)
        st = m.get("status")
        if st in ("creator", "member") or (st == "administrator" and m.get("can_post_messages", True) is not False):
            return True, "Tayyor", ch.get("title", "")
        return False, "Bot bu guruhda xabar yubora olmaydi (admin qiling).", ch.get("title", "")
    except TgError as e:
        return False, f"Guruhga kirib bo'lmadi: {e.description}"[:160], ""


DEFAULT_COMMANDS = [{"command": "start", "description": "Botni boshlash"}, {"command": "menu", "description": "Bosh menyu"},
                    {"command": "status", "description": "Obuna holatim"}]


def publish_bot(project) -> list[dict]:
    """Botni to'liq sozlaydi: token tekshirish, profil, buyruqlar, guruhlar. Natija — tekshiruv ro'yxati."""
    checks = []

    def add(key, label, ok, msg=""):
        checks.append({"key": key, "label": label, "ok": bool(ok), "msg": msg})

    api = get_api(project)
    if not api:
        add("token", "Bot tokeni", False, "Token kiritilmagan.")
    else:
        try:
            me = api.get_me()
            project.bot_id, project.bot_username, project.bot_title = me["id"], me.get("username", ""), (project.bot_title or me.get("first_name", ""))[:80]
            add("token", "Bot tokeni", True, f"@{project.bot_username}")
        except TgError as e:
            add("token", "Bot tokeni", False, f"Token yaroqsiz: {e.description}")
            api = None
    if api:
        def step(key, label, fn, hint=""):
            try:
                fn()
                add(key, label, True)
            except TgError as e:
                add(key, label, False, (hint or e.description)[:200])
        step("webhook", "Yangilanishlarni qabul qilish (polling)", api.delete_webhook)
        if project.bot_title:
            step("name", "Bot nomi", lambda: api.set_name(project.bot_title))
        step("about", "Qisqa tavsif (About)", lambda: api.set_about(project.about))
        step("desc", "Tavsif (Description)", lambda: api.set_description(project.description))
        cmds = project.commands or DEFAULT_COMMANDS
        step("cmds", "Buyruqlar", lambda: api.set_commands(cmds))
        for a in project.admins.all():
            try:
                api.set_commands([*cmds, {"command": "stat", "description": "Statistika (admin)"}], {"type": "chat", "chat_id": a.tg_id})
            except TgError:
                pass
        step("menu", "Menyu tugmasi", api.set_menu_button)
        if project.avatar:
            step("avatar", "Bot rasmi", lambda: api.set_photo(project.avatar.path),
                 "Rasmni Bot API orqali o'rnatib bo'lmadi. @BotFather → /mybots → botni tanlang → Edit Bot → Edit Botpic orqali qo'ying.")
        bid = project.bot_id
        if project.leads_chat_id:
            ok, msg, title = check_post_chat(api, project.leads_chat_id, bid)
            project.leads_chat_title = title or project.leads_chat_title
            add("leads", "Leadlar guruhi", ok, msg)
        else:
            add("leads", "Leadlar guruhi", False, "Ulanmagan (lead postlari yuborilmaydi).")
        if project.pay_chat_id:
            ok, msg, title = check_post_chat(api, project.pay_chat_id, bid)
            project.pay_chat_title = title or project.pay_chat_title
            add("payarch", "To'lovlar arxivi guruhi", ok, msg)
        gs = list(project.groups.all())
        if not gs:
            add("groups", "Yopiq guruh", False, "Hech qaysi guruh ulanmagan.")
        for g in gs:
            add(f"group{g.pk}", f"Yopiq guruh: {g.title or g.chat_id}", check_group(project, api, g), g.note)
    add("admins", "Mas'ul admin", project.admins.exists(), "" if project.admins.exists() else "To'lovni tasdiqlaydigan admin biriktirilmagan.")
    add("tariffs", "Tariflar", project.tariffs.filter(is_active=True).exists(), "" if project.tariffs.filter(is_active=True).exists() else "Kamida bitta tarif kerak.")
    add("card", "To'lov kartasi", bool(project.card_number), "" if project.card_number else "Karta raqami kiritilmagan.")
    project.last_check, project.last_check_at = checks, timezone.now()
    token_ok = next((c["ok"] for c in checks if c["key"] == "token"), False)
    if token_ok and project.status == "draft":
        project.status = "active"
    project.last_error = "" if token_ok else "Token yaroqsiz yoki kiritilmagan"
    project.save()
    event(project, "publish", f"Bot sozlandi: {sum(1 for c in checks if c['ok'])}/{len(checks)} tekshiruv muvaffaqiyatli")
    return checks


def publish_flow(project, user=None, note: str = "") -> None:
    """Qoralamani joriy qiladi (eskisi versiya sifatida saqlanadi)."""
    from .models import FlowVersion
    if project.flow:
        FlowVersion.objects.create(project=project, data=project.flow, note=note or "Joriy qilishdan oldingi", by=user)
    if project.flow_draft:
        project.flow = project.flow_draft
    project.flow_draft = None
    project.flow_published_at = timezone.now()
    project.save(update_fields=["flow", "flow_draft", "flow_published_at"])
    event(project, "flow", "Bot oqimi joriy qilindi")


def media_for(project, media_id):
    return OnlineMedia.objects.filter(project=project, pk=media_id).first() if media_id else None


def lead_events(lead, n=30):
    return lead.events.all()[:n]
