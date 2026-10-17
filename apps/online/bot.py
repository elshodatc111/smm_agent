"""Onlayn kanal botlari: yangilanishlarni qayta ishlash (`handle_update` — testlanadi) va worker ichidagi long-polling sikli."""
from __future__ import annotations

import logging
import threading
import time

from django.db import close_old_connections
from django.utils import timezone

from . import ai as mentor
from . import defaults as D
from . import services as S
from .models import Lead, OnlineMedia, OnlineProject, ProjectAdmin, Tariff
from .tgapi import BotAPI, TgError, get_api

log = logging.getLogger(__name__)


def _texts(project):
    return D.get_flow(project)["texts"]


# ───────────────────────── ekranlar ─────────────────────────
def _media_payload(m: OnlineMedia):
    if m.tg_file_id:
        return m.tg_file_id
    with open(m.file.path, "rb") as f:
        return (m.file.name.rsplit("/", 1)[-1], f.read())


def _remember_file_id(m: OnlineMedia, res: dict):
    fid = (res.get("photo") or [{}])[-1].get("file_id") if res.get("photo") else (res.get("video") or {}).get("file_id")
    if fid and fid != m.tg_file_id:
        m.tg_file_id = fid
        m.save(update_fields=["tg_file_id"])


def send_screen(api, project, chat_id, key, lead=None, staff=False, extra_rows=None, reply_markup=None, flow=None):
    flow = flow or D.get_flow(project)
    scr = flow["screens"].get(key) or flow["screens"]["menu"]
    vals = S.user_vals(project, lead) if lead else dict(name="", project=S.esc(project.name), bot=project.bot_username)
    text = D.fmt(scr["text"], **vals)
    rows = [list(r) for r in scr["rows"]]
    markup = D.markup_for(rows, staff)
    if key == "menu" and staff:
        markup = markup or {"inline_keyboard": []}
        markup["inline_keyboard"].append([{"text": "📈 Statistika", "callback_data": "stat"}])
    if extra_rows:
        markup = markup or {"inline_keyboard": []}
        markup["inline_keyboard"].extend(extra_rows)
    if reply_markup is not None:
        markup = reply_markup
    if key == "phone":
        markup = {"keyboard": [[{"text": scr.get("btn") or "📱 Raqamni yuborish", "request_contact": True}]], "resize_keyboard": True, "one_time_keyboard": True}
    media = S.media_for(project, scr.get("media"))
    if media:
        try:
            cap = text if len(text) <= 1024 else ""
            try:
                res = api.send_media(chat_id, media.kind, _media_payload(media), caption=cap, markup=markup if cap or not text else None)
            except TgError:
                if media.tg_file_id:      # file_id eskirgan — qayta yuklaymiz
                    media.tg_file_id = ""
                    res = api.send_media(chat_id, media.kind, _media_payload(media), caption=cap, markup=markup if cap or not text else None)
                else:
                    raise
            _remember_file_id(media, res)
            if text and not cap:
                api.send(chat_id, text, markup)
            return res
        except (TgError, OSError, ValueError) as e:
            log.warning("media yuborilmadi: %s", e)
    return api.send(chat_id, text, markup)


def _send(api, chat_id, text, markup=None):
    try:
        return api.send(chat_id, text, markup)
    except TgError as e:
        log.warning("yuborilmadi %s: %s", chat_id, e)
        return None


# ───────────────────────── yangilanishlar ─────────────────────────
def handle_update(project: OnlineProject, upd: dict, api) -> None:
    if "message" in upd:
        _on_message(project, upd["message"], api)
    elif "callback_query" in upd:
        _on_callback(project, upd["callback_query"], api)
    elif "chat_join_request" in upd:
        _on_join_request(project, upd["chat_join_request"], api)
    elif "chat_member" in upd:
        _on_chat_member(project, upd["chat_member"], api)
    elif "my_chat_member" in upd:
        _on_my_member(project, upd["my_chat_member"])


def _group_ids(project):
    return set(project.groups.values_list("chat_id", flat=True))


def _on_message(project, msg, api):
    chat = msg.get("chat") or {}
    frm = msg.get("from") or {}
    if not frm or frm.get("is_bot"):
        return
    text = (msg.get("text") or "").strip()
    if chat.get("type") != "private":
        if text.split("@")[0] == "/id":
            _send(api, chat["id"], f"Bu guruhning ID raqami: <code>{chat['id']}</code>\nUni panelda «Guruhlar» bo'limiga kiriting.")
        for u in msg.get("new_chat_members") or []:
            if chat["id"] in _group_ids(project) and not u.get("is_bot"):
                _guard_member(project, api, chat["id"], u["id"])
        return
    _private(project, msg, frm, text, api)


def _private(project, msg, frm, text, api):
    cid = msg["chat"]["id"]
    staff = ProjectAdmin.objects.filter(project=project, tg_id=frm["id"]).first()
    cmd = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    payload = text.split(maxsplit=1)[1].strip() if cmd == "/start" and len(text.split(maxsplit=1)) > 1 else ""
    lead, created = S.upsert_lead(project, frm, payload if cmd == "/start" else "", api)
    T = _texts(project)
    if lead.blocked:
        _send(api, cid, T["blocked"])
        return
    # admin: rad etish sababi kutilmoqda
    if staff and staff.awaiting.get("type") == "reject" and not cmd:
        pid = staff.awaiting.get("payment")
        staff.awaiting = {}
        staff.save(update_fields=["awaiting"])
        reason = "" if text in ("-", "") else text[:300]
        ok, m = S.decide_payment(project, api, pid, False, staff.name or str(staff.tg_id), reason)
        _send(api, cid, f"{'❌ Rad etildi' if ok else m}")
        return
    if cmd == "/start":
        if not created:
            lead.starts += 1
        lead.awaiting, lead.ai_active = {}, False
        lead.save(update_fields=["starts", "awaiting", "ai_active"])
        send_screen(api, project, cid, "start", lead, bool(staff))
        if project.ask_phone and not lead.phone:
            send_screen(api, project, cid, "phone", lead)
        else:
            send_screen(api, project, cid, "menu", lead, bool(staff))
            if lead.phone:
                S.post_lead(project, api, lead, activity=True)
        return
    if cmd == "/menu":
        lead.awaiting, lead.ai_active = {}, False
        lead.save(update_fields=["awaiting", "ai_active"])
        send_screen(api, project, cid, "menu", lead, bool(staff))
        return
    if cmd == "/status":
        _status(project, api, cid, lead)
        return
    if cmd == "/stat":
        _stat(project, api, cid, staff)
        return
    if msg.get("contact"):
        c = msg["contact"]
        if c.get("user_id") and c["user_id"] != frm["id"]:
            _send(api, cid, T["phone_bad"])
            return
        S.set_phone(project, lead, c.get("phone_number", ""), api)
        _send(api, cid, T["phone_thanks"], {"remove_keyboard": True})
        send_screen(api, project, cid, "menu", lead, bool(staff))
        return
    if lead.awaiting.get("type") == "receipt" and not cmd:
        _receipt(project, api, cid, lead, msg)
        return
    if lead.ai_active and text and not cmd:
        _ai(project, api, cid, lead, text)
        return
    if project.ask_phone and not lead.phone:
        send_screen(api, project, cid, "phone", lead)
        return
    _send(api, cid, T["unknown"])


def _receipt(project, api, cid, lead, msg):
    T = _texts(project)
    fid = uid = ""
    if msg.get("photo"):
        ph = msg["photo"][-1]
        fid, uid = ph["file_id"], ph.get("file_unique_id", "")
    elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
        d = msg["document"]
        fid, uid = d["file_id"], d.get("file_unique_id", "")
    if not fid:
        _send(api, cid, T["need_photo"])
        return
    tariff = Tariff.objects.filter(project=project, pk=lead.awaiting.get("tariff"), is_active=True).first()
    if not tariff:
        lead.awaiting = {}
        lead.save(update_fields=["awaiting"])
        send_screen(api, project, cid, "menu", lead)
        return
    lead.awaiting = {}
    lead.save(update_fields=["awaiting"])
    S.create_payment(project, api, lead, tariff, fid, uid)
    _send(api, cid, T["pay_wait"])


def _ai(project, api, cid, lead, text):
    T = _texts(project)
    if not project.ai_enabled:
        _send(api, cid, T["ai_off"])
        return
    try:
        ans = mentor.mentor_answer(project, lead, text)
        _send(api, cid, S.esc(ans) if ans else T["ai_error"])
    except mentor.AiLimit as e:
        _send(api, cid, D.fmt(T["ai_limit"], limit=e.limit))
    except Exception as e:  # noqa: BLE001
        log.warning("AI mentor xatosi: %s", e)
        _send(api, cid, T["ai_error"])


def _status(project, api, cid, lead):
    T = _texts(project)
    sub = S.active_sub(lead)
    if sub:
        _send(api, cid, D.fmt(T["status_active"], **S.user_vals(project, lead, sub.tariff, sub)))
    else:
        _send(api, cid, T["no_sub"])


def _stat(project, api, cid, staff):
    if not (staff and staff.can_stats):
        _send(api, cid, _texts(project)["stat_denied"])
        return
    _send(api, cid, S.stats_text(project))


def _tariff_list(project, api, cid, lead):
    T = _texts(project)
    ts = list(project.tariffs.filter(is_active=True))
    if not ts:
        _send(api, cid, T["no_tariffs"])
        return
    rows = [[{"text": f"{t.name} — {D.money(t.price)} so'm", "callback_data": f"t:{t.pk}"}] for t in ts]
    rows.append([{"text": "⬅️ Bosh menyu", "callback_data": "s:menu"}])
    lines = [T["tariffs_title"], ""] + [f"• <b>{S.esc(t.name)}</b> — {D.money(t.price)} so'm / {t.days} kun" + (f"\n  {S.esc(t.description)}" if t.description else "") for t in ts]
    _send(api, cid, "\n".join(lines), {"inline_keyboard": rows})


def _on_callback(project, cb, api):
    frm = cb.get("from") or {}
    msg = cb.get("message") or {}
    cid = (msg.get("chat") or {}).get("id")
    data = cb.get("data") or ""
    if not cid:
        return
    staff = ProjectAdmin.objects.filter(project=project, tg_id=frm["id"]).first()
    T = _texts(project)
    if data[:4] in ("pok:", "pno:"):
        if not staff:
            api.answer(cb["id"], T["stat_denied"], True)
            return
        pid = int(data[4:] or 0)
        by = staff.name or str(staff.tg_id)
        if data.startswith("pok:"):
            ok, m = S.decide_payment(project, api, pid, True, by)
            api.answer(cb["id"], "✅ Tasdiqlandi" if ok else m, not ok)
        else:
            p = project.payments.filter(pk=pid).first()
            if not p or p.status != "pending":
                api.answer(cb["id"], "Bu to'lov allaqachon ko'rib chiqilgan.", True)
                return
            staff.awaiting = {"type": "reject", "payment": pid}
            staff.save(update_fields=["awaiting"])
            api.answer(cb["id"])
            _send(api, cid, f"❌ To'lov #{pid} uchun rad etish sababini yozing (sababsiz rad etish uchun «-» yuboring):")
        return
    api.answer(cb["id"])
    lead, _ = S.upsert_lead(project, frm, "", api)
    if lead.blocked:
        return
    if data.startswith("s:"):
        lead.ai_active = False
        lead.save(update_fields=["ai_active"])
        send_screen(api, project, cid, data[2:], lead, bool(staff))
    elif data == "tariffs":
        _tariff_list(project, api, cid, lead)
    elif data.startswith("t:"):
        t = project.tariffs.filter(pk=int(data[2:] or 0), is_active=True).first()
        if not t:
            return
        if not project.card_number:
            _send(api, cid, T["pay_no_card"])
            return
        lead.awaiting = {"type": "receipt", "tariff": t.pk}
        lead.ai_active = False
        lead.save(update_fields=["awaiting", "ai_active"])
        if lead.status in ("new", "phone"):
            lead.status = "interested"
            lead.save(update_fields=["status"])
        _send(api, cid, D.fmt(T["pay_info"], **S.user_vals(project, lead, t)), {"inline_keyboard": [[{"text": "⬅️ Tariflarga qaytish", "callback_data": "tariffs"}]]})
    elif data == "status":
        _status(project, api, cid, lead)
    elif data == "join":
        if S.has_access(project, lead, frm["id"]):
            links = S.invite_links(project, api, lead)
            if links:
                _send(api, cid, T["join_links"], {"inline_keyboard": [[{"text": f"➡️ {t}", "url": u}] for t, u in links]})
            else:
                _send(api, cid, T["no_groups"])
        else:
            _send(api, cid, T["no_sub"])
    elif data == "ai":
        if not project.ai_enabled:
            _send(api, cid, T["ai_off"])
            return
        lead.ai_active, lead.awaiting = True, {}
        lead.save(update_fields=["ai_active", "awaiting"])
        _send(api, cid, T["ai_intro"])
    elif data == "stat":
        _stat(project, api, cid, staff)


# ───────────────────────── guruh nazorati ─────────────────────────
def _on_join_request(project, req, api):
    chat_id = (req.get("chat") or {}).get("id")
    if chat_id not in _group_ids(project):
        return
    uid = req["from"]["id"]
    lead = Lead.objects.filter(project=project, tg_id=uid).first()
    try:
        if S.has_access(project, lead, uid):
            api.approve_join(chat_id, uid)
            S.event(project, "join_ok", f"{lead.full_name if lead else uid}: guruhga qabul qilindi", lead)
        else:
            api.decline_join(chat_id, uid)
            S.event(project, "join_no", f"{uid}: obunasiz — so'rov rad etildi", lead)
            if req.get("user_chat_id"):
                _send(api, req["user_chat_id"], _texts(project)["join_denied"])
    except TgError as e:
        S.event(project, "error", f"Qo'shilish so'rovi: {e.description}", lead)


def _guard_member(project, api, chat_id, uid):
    lead = Lead.objects.filter(project=project, tg_id=uid).first()
    if S.has_access(project, lead, uid):
        return
    try:
        st = api.get_member(chat_id, uid).get("status")
        if st in ("administrator", "creator"):
            return
        api.kick(chat_id, uid)
        S.event(project, "kick", f"{lead.full_name if lead else uid}: obunasiz kirgani uchun guruhdan chiqarildi", lead)
    except TgError as e:
        S.event(project, "error", f"Chiqarib bo'lmadi ({uid}): {e.description}", lead)


def _on_chat_member(project, upd, api):
    chat_id = (upd.get("chat") or {}).get("id")
    if chat_id not in _group_ids(project):
        return
    new = upd.get("new_chat_member") or {}
    u = new.get("user") or {}
    if new.get("status") in ("member", "restricted") and not u.get("is_bot") and u.get("id"):
        _guard_member(project, api, chat_id, u["id"])


def _on_my_member(project, upd):
    if (upd.get("chat") or {}).get("type") == "private":
        Lead.objects.filter(project=project, tg_id=upd["chat"]["id"]).update(bot_blocked=upd.get("new_chat_member", {}).get("status") in ("kicked", "left"))


# ───────────────────────── polling sikli (worker ichida) ─────────────────────────
def poll_project(pid: int, stop: threading.Event) -> None:
    last_maint, wait, errs = 0.0, 0, 0
    while not stop.is_set():
        try:
            close_old_connections()
            project = OnlineProject.objects.filter(pk=pid, status="active").first()
            if not project or not project.token_enc:
                return
            api = get_api(project)
            if time.time() - last_maint > 60:
                S.maintenance(project, api)
                last_maint = time.time()
            ups = api.get_updates(project.update_offset, 20)
            errs = 0
            for u in ups:
                try:
                    handle_update(project, u, api)
                except Exception:  # noqa: BLE001
                    log.exception("online update xatosi (loyiha %s)", pid)
                project.update_offset = u["update_id"] + 1
                OnlineProject.objects.filter(pk=pid).update(update_offset=project.update_offset)
        except TgError as e:
            errs += 1
            if e.code == 401:
                OnlineProject.objects.filter(pk=pid).update(last_error="Token yaroqsiz (401). Panelda yangilang.", status="paused")
                return
            stop.wait(min(60, 5 * errs))
        except Exception as e:  # noqa: BLE001
            errs += 1
            log.warning("online polling (%s): %s", pid, e)
            stop.wait(min(60, 5 * errs))
        finally:
            close_old_connections()


def run_online_loop(stop: threading.Event) -> None:
    """Faol loyihalarning har biri uchun alohida oqim ochadi; yangi/to'xtatilgan loyihalarni 15 soniyada bir tekshiradi."""
    threads: dict[int, threading.Thread] = {}
    while not stop.is_set():
        try:
            close_old_connections()
            ids = set(OnlineProject.objects.filter(status="active").exclude(token_enc="").values_list("pk", flat=True))
            for pid in ids:
                t = threads.get(pid)
                if not t or not t.is_alive():
                    t = threading.Thread(target=poll_project, args=(pid, stop), daemon=True, name=f"online{pid}")
                    threads[pid] = t
                    t.start()
        except Exception as e:  # noqa: BLE001
            log.warning("online manager: %s", e)
        finally:
            close_old_connections()
        stop.wait(15)
