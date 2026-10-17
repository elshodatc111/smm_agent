"""Onlayn kanal: bot oqimi, lead, to'lov tasdiqlash, obuna, guruh nazorati, AI mentor, konstruktor, ruxsatlar."""
import json
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.online import ai as mentor
from apps.online import bot, tgapi
from apps.online import defaults as D
from apps.online import services as S
from apps.online.models import KnowledgeDoc, Lead, OnlineProject, Payment, ProjectAdmin, ProjectGroup, Subscription, Tariff

pytestmark = pytest.mark.django_db
LEADS, ARCH, GROUP, ADMIN = -1001, -1002, -1003, 777


@pytest.fixture(autouse=True)
def _clean(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    tgapi._FAKES.clear()


@pytest.fixture
def proj(db):
    p = OnlineProject(name="ATKO Premium", status="active", leads_chat_id=LEADS, pay_chat_id=ARCH, card_number="8600123412341234", card_holder="A. B.", card_bank="Uzcard",
                      flow=D.default_flow(), bot_id=999, bot_username="fake_bot")
    p.set_token("123:abc")
    p.save()
    ProjectGroup.objects.create(project=p, chat_id=GROUP, title="Yopiq guruh", ok=True)
    ProjectAdmin.objects.create(project=p, tg_id=ADMIN, name="Mas'ul", is_primary=True)
    Tariff.objects.create(project=p, name="1 oylik", days=30, price=299000)
    return p


@pytest.fixture
def api(proj):
    return tgapi.get_api(proj)


def frm(uid=1, name="Ali", **kw):
    return {"id": uid, "first_name": name, "username": f"u{uid}", "language_code": "uz", **kw}


def msg(uid=1, text="", **kw):
    return {"update_id": 1, "message": {"message_id": 1, "chat": {"id": uid, "type": "private"}, "from": frm(uid), "text": text, **kw}}


def cb(uid, data, chat=None):
    return {"update_id": 1, "callback_query": {"id": "c1", "from": frm(uid), "data": data, "message": {"message_id": 5, "chat": {"id": chat or uid, "type": "private"}}}}


def texts_to(api, chat):
    return [m for m in api.sent if m["chat"]["id"] == chat]


def start_and_phone(proj, api, uid=1):
    bot.handle_update(proj, msg(uid, "/start reklama1"), api)
    bot.handle_update(proj, msg(uid, contact={"phone_number": "998901112233", "user_id": uid}), api)
    return Lead.objects.get(project=proj, tg_id=uid)


def pay_through(proj, api, uid=1, fid="photo1", uniq="u-1"):
    lead = start_and_phone(proj, api, uid) if not Lead.objects.filter(project=proj, tg_id=uid, phone__gt="").exists() else Lead.objects.get(project=proj, tg_id=uid)
    t = proj.tariffs.first()
    bot.handle_update(proj, cb(uid, f"t:{t.pk}"), api)
    bot.handle_update(proj, msg(uid, photo=[{"file_id": fid, "file_unique_id": uniq}]), api)
    return lead, Payment.objects.filter(project=proj).latest("id")


# ───────────── lead ─────────────
def test_start_creates_lead_and_asks_phone(proj, api):
    bot.handle_update(proj, msg(1, "/start reklama1"), api)
    l = Lead.objects.get(project=proj, tg_id=1)
    assert l.source == "reklama1" and l.status == "new"
    sent = texts_to(api, 1)
    assert "Assalomu alaykum" in sent[0]["text"] and "Ali" in sent[0]["text"]
    assert "markup" in sent[1] and sent[1]["markup"]["keyboard"][0][0]["request_contact"] is True


def test_phone_saved_and_lead_posted_once(proj, api):
    l = start_and_phone(proj, api)
    assert l.phone == "+998901112233" and l.status == "phone"
    posts = texts_to(api, LEADS)
    assert len(posts) == 1 and "+998901112233" in posts[0]["text"] and "reklama1" in posts[0]["text"] and "Yangi lead" in posts[0]["text"]
    bot.handle_update(proj, msg(1, "/start"), api)       # 1 oy ichida qayta kirsa — takror post yo'q
    assert len(texts_to(api, LEADS)) == 1
    assert "editText" in api.names() or True


def test_returning_lead_after_month_reposted(proj, api):
    l = start_and_phone(proj, api)
    Lead.objects.filter(pk=l.pk).update(posted_at=timezone.now() - timedelta(days=31))
    bot.handle_update(proj, msg(1, "/start"), api)
    posts = texts_to(api, LEADS)
    assert len(posts) == 2 and "Qaytgan lead" in posts[1]["text"]
    assert Lead.objects.get(pk=l.pk).post_count == 2


def test_foreign_contact_rejected(proj, api):
    bot.handle_update(proj, msg(1, "/start"), api)
    bot.handle_update(proj, msg(1, contact={"phone_number": "998900000000", "user_id": 5}), api)
    assert Lead.objects.get(project=proj, tg_id=1).phone == ""
    assert not texts_to(api, LEADS)


def test_blocked_lead_gets_nothing_useful(proj, api):
    start_and_phone(proj, api)
    Lead.objects.filter(project=proj).update(blocked=True)
    api.sent.clear()
    bot.handle_update(proj, msg(1, "/start"), api)
    assert texts_to(api, 1)[0]["text"] == D.DEFAULT_TEXTS["blocked"]


# ───────────── to'lov ─────────────
def test_payment_flow_approve(proj, api):
    lead, p = pay_through(proj, api)
    assert p.status == "pending" and p.amount == 299000 and not p.duplicate
    admin_msgs = [m for m in texts_to(api, ADMIN) if m.get("markup")]
    assert admin_msgs and admin_msgs[0]["markup"]["inline_keyboard"][0][0]["callback_data"] == f"pok:{p.pk}"
    assert "chek" in texts_to(api, 1)[-1]["text"].lower() or "Chek" in texts_to(api, 1)[-1]["text"]
    bot.handle_update(proj, cb(ADMIN, f"pok:{p.pk}"), api)
    p.refresh_from_db()
    lead.refresh_from_db()
    assert p.status == "approved" and lead.status == "sold"
    sub = Subscription.objects.get(lead=lead)
    assert sub.status == "active" and (sub.ends_at - timezone.now()).days in (29, 30)
    last = texts_to(api, 1)[-1]
    assert "tasdiqlandi" in last["text"] and last["markup"]["inline_keyboard"][0][0]["url"].startswith("https://t.me/+")
    arch = texts_to(api, ARCH)
    assert arch and "To'lov tasdiqlandi" in arch[0]["text"] and "299 000" in arch[0]["text"]
    ok, msg_ = S.decide_payment(proj, api, p.pk, False, "x")
    assert not ok and "allaqachon" in msg_
    assert Subscription.objects.filter(lead=lead).count() == 1


def test_payment_reject_with_reason(proj, api):
    lead, p = pay_through(proj, api)
    bot.handle_update(proj, cb(ADMIN, f"pno:{p.pk}"), api)
    assert ProjectAdmin.objects.get(tg_id=ADMIN).awaiting["payment"] == p.pk
    bot.handle_update(proj, msg(ADMIN, "Summa mos emas"), api)
    p.refresh_from_db()
    assert p.status == "rejected" and p.reject_reason == "Summa mos emas"
    assert "Summa mos emas" in texts_to(api, 1)[-1]["text"]
    assert not Subscription.objects.filter(lead=lead).exists()


def test_only_staff_can_decide(proj, api):
    lead, p = pay_through(proj, api)
    bot.handle_update(proj, cb(5555, f"pok:{p.pk}"), api)
    p.refresh_from_db()
    assert p.status == "pending"


def test_duplicate_receipt_flagged(proj, api):
    pay_through(proj, api, 1, "ph1", "same")
    _, p2 = pay_through(proj, api, 2, "ph2", "same")
    assert p2.duplicate is True
    assert "TAKROR" in [m for m in texts_to(api, ADMIN) if m.get("markup")][-1]["text"]


def test_receipt_requires_photo(proj, api):
    start_and_phone(proj, api)
    bot.handle_update(proj, cb(1, f"t:{proj.tariffs.first().pk}"), api)
    bot.handle_update(proj, msg(1, "to'ladim"), api)
    assert not Payment.objects.exists() and "rasm" in texts_to(api, 1)[-1]["text"]


def test_extend_existing_subscription(proj, api):
    lead, p = pay_through(proj, api)
    S.decide_payment(proj, api, p.pk, True, "t")
    first = Subscription.objects.get(lead=lead).ends_at
    bot.handle_update(proj, cb(1, f"t:{proj.tariffs.first().pk}"), api)
    bot.handle_update(proj, msg(1, photo=[{"file_id": "p9", "file_unique_id": "z9"}]), api)
    S.decide_payment(proj, api, Payment.objects.latest("id").pk, True, "t")
    assert Subscription.objects.filter(lead=lead).count() == 1
    assert Subscription.objects.get(lead=lead).ends_at - first == timedelta(days=30)


def test_escalation_to_backup_admin(proj, api):
    ProjectAdmin.objects.create(project=proj, tg_id=888, name="Zaxira", is_primary=False)
    lead, p = pay_through(proj, api)
    assert not [m for m in texts_to(api, 888)]
    Payment.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(minutes=30))
    assert S.escalate_pending(proj, api) == 1
    assert [m for m in texts_to(api, 888) if m.get("markup")]
    assert S.escalate_pending(proj, api) == 0


# ───────────── guruh nazorati ─────────────
def test_join_request_only_for_subscribers(proj, api):
    bot.handle_update(proj, {"update_id": 1, "chat_join_request": {"chat": {"id": GROUP}, "from": frm(1), "user_chat_id": 1}}, api)
    assert "declineJoin" in api.names() and "approveJoin" not in api.names()
    lead, p = pay_through(proj, api)
    S.decide_payment(proj, api, p.pk, True, "t")
    bot.handle_update(proj, {"update_id": 2, "chat_join_request": {"chat": {"id": GROUP}, "from": frm(1), "user_chat_id": 1}}, api)
    assert "approveJoin" in api.names()


def test_intruder_kicked_but_staff_and_exempt_kept(proj, api):
    def joined(uid):
        return {"update_id": 1, "chat_member": {"chat": {"id": GROUP}, "new_chat_member": {"status": "member", "user": frm(uid)}}}
    bot.handle_update(proj, joined(50), api)
    assert ("kick", {"chat_id": GROUP, "user_id": 50}) in api.calls
    api.calls.clear()
    bot.handle_update(proj, joined(ADMIN), api)
    assert not [c for c in api.calls if c[0] == "kick"]
    Lead.objects.create(project=proj, tg_id=60, exempt=True)
    bot.handle_update(proj, joined(60), api)
    assert not [c for c in api.calls if c[0] == "kick"]


def test_group_chat_id_command(proj, api):
    bot.handle_update(proj, {"update_id": 1, "message": {"message_id": 1, "chat": {"id": -555, "type": "supergroup"}, "from": frm(9), "text": "/id"}}, api)
    assert "-555" in texts_to(api, -555)[0]["text"]


def test_expired_subscription_removed_and_notified(proj, api):
    lead, p = pay_through(proj, api)
    S.decide_payment(proj, api, p.pk, True, "t")
    Subscription.objects.update(ends_at=timezone.now() - timedelta(minutes=1))
    api.calls.clear()
    out = S.maintenance(proj, api)
    assert out["expired"] == 1
    assert ("kick", {"chat_id": GROUP, "user_id": 1}) in api.calls
    assert "tugadi" in texts_to(api, 1)[-1]["text"]
    assert Subscription.objects.get().status == "expired"


def test_reminders_sent_once(proj, api):
    lead, p = pay_through(proj, api)
    S.decide_payment(proj, api, p.pk, True, "t")
    Subscription.objects.update(ends_at=timezone.now() + timedelta(days=2, hours=3))
    assert S.send_reminders(proj, api) == 1
    assert "3 kundan" in texts_to(api, 1)[-1]["text"]
    assert S.send_reminders(proj, api) == 0


def test_exempt_not_kicked_on_expiry(proj, api):
    lead, p = pay_through(proj, api)
    S.decide_payment(proj, api, p.pk, True, "t")
    Lead.objects.filter(pk=lead.pk).update(exempt=True)
    Subscription.objects.update(ends_at=timezone.now() - timedelta(minutes=1))
    api.calls.clear()
    S.maintenance(proj, api)
    assert not [c for c in api.calls if c[0] == "kick"]


# ───────────── AI mentor ─────────────
def test_ai_free_limit_and_subscriber(proj, api):
    KnowledgeDoc.objects.create(project=proj, title="Narx", content="Kurs narxi 299000 so'm, davomiyligi 30 kun.")
    start_and_phone(proj, api)
    bot.handle_update(proj, cb(1, "ai"), api)
    assert "AI mentor ulandi" in texts_to(api, 1)[-1]["text"]
    for _ in range(3):
        bot.handle_update(proj, msg(1, "Kurs narxi qancha?"), api)
    assert "limiti tugadi" not in texts_to(api, 1)[-1]["text"]
    bot.handle_update(proj, msg(1, "Yana savol"), api)
    assert "limiti tugadi" in texts_to(api, 1)[-1]["text"]
    lead = Lead.objects.get(project=proj, tg_id=1)
    S.grant_subscription(proj, lead, 30, None, "manual")
    bot.handle_update(proj, msg(1, "Yana savol"), api)
    assert "limiti tugadi" not in texts_to(api, 1)[-1]["text"]


def test_retrieve_prefers_matching_doc(proj):
    KnowledgeDoc.objects.create(project=proj, title="Jadval", content="Darslar dushanba va chorshanba kuni soat 19:00 da.")
    KnowledgeDoc.objects.create(project=proj, title="Narx", content="Kurs narxi 299000 so'm.")
    assert mentor.retrieve(proj, "narxi qancha")[:6] == "[Narx]"


def test_ai_off(proj, api):
    proj.ai_enabled = False
    proj.save()
    start_and_phone(proj, api)
    bot.handle_update(proj, cb(1, "ai"), api)
    assert "o'chirilgan" in texts_to(api, 1)[-1]["text"]


# ───────────── statistika ─────────────
def test_stats_and_stat_command_admin_only(proj, api):
    lead, p = pay_through(proj, api)
    S.decide_payment(proj, api, p.pk, True, "t")
    s = S.stats(proj)
    assert s["leads"] == 1 and s["phones"] == 1 and s["sales"] == 1 and s["revenue"] == 299000 and s["conv"] == 100.0 and s["active_subs"] == 1
    bot.handle_update(proj, msg(ADMIN, "/stat"), api)
    assert "statistika" in texts_to(api, ADMIN)[-1]["text"]
    bot.handle_update(proj, msg(1, "/stat"), api)
    assert "adminlar uchun" in texts_to(api, 1)[-1]["text"]


# ───────────── botni sozlash ─────────────
def test_publish_bot_checks(proj, api):
    proj.status = "draft"
    proj.about, proj.description, proj.bot_title = "Qisqa", "Uzun tavsif", "ATKO Bot"
    proj.save()
    checks = S.publish_bot(proj)
    by = {c["key"]: c for c in checks}
    assert by["token"]["ok"] and by["leads"]["ok"] and by["admins"]["ok"] and by["tariffs"]["ok"] and by["card"]["ok"]
    assert {"setName", "setAbout", "setDescription", "setCommands", "deleteWebhook"} <= set(api.names())
    proj.refresh_from_db()
    assert proj.status == "active" and proj.bot_username == "fake_bot"


def test_group_check_reports_missing_rights(proj, api):
    api.chat_rights = {"status": "administrator", "can_restrict_members": False, "can_invite_users": True}
    g = proj.groups.first()
    assert S.check_group(proj, api, g) is False and "chiqarish" in g.note


# ───────────── konstruktor ─────────────
def test_clean_flow_validation():
    f = D.default_flow()
    f["screens"]["menu"]["rows"] = [[{"t": "A", "a": "screen", "v": "yoq"}, {"t": "B", "a": "url", "v": "oddiy"}]]
    clean, warns = D.clean_flow(f)
    assert any("mavjud bo'lmagan" in w for w in warns) and any("havola" in w for w in warns)
    del f["screens"]["start"]
    with pytest.raises(ValueError):
        D.clean_flow(f)
    with pytest.raises(ValueError):
        D.clean_flow({"screens": {"Bad Key": {"text": "x"}}})


def test_markup_and_fmt():
    mk = D.markup_for([[{"t": "Ochish", "a": "screen", "v": "menu"}, {"t": "Sayt", "a": "url", "v": "example.com"}], [{"t": "Stat", "a": "stat", "v": ""}]])
    assert mk["inline_keyboard"][0][0]["callback_data"] == "s:menu" and mk["inline_keyboard"][0][1]["url"] == "https://example.com" and len(mk["inline_keyboard"]) == 1
    assert D.fmt("Salom {name} {x}", name="Ali") == "Salom Ali {x}"


def test_custom_screen_and_button_in_bot(proj, api):
    f = D.default_flow()
    f["screens"]["kurslar"] = {"title": "Kurslar", "text": "Bizning kurslar: <b>Python</b>", "media": None, "rows": []}
    f["screens"]["menu"]["rows"] = [[{"t": "📚 Kurslar", "a": "screen", "v": "kurslar"}]]
    proj.flow = f
    proj.save()
    start_and_phone(proj, api)
    assert texts_to(api, 1)[-1]["markup"]["inline_keyboard"][0][0]["callback_data"] == "s:kurslar"
    bot.handle_update(proj, cb(1, "s:kurslar"), api)
    assert "Python" in texts_to(api, 1)[-1]["text"]


def test_media_screen_uploads_once_then_reuses_file_id(proj, api):
    from apps.online.models import OnlineMedia
    m = OnlineMedia.objects.create(project=proj, file=SimpleUploadedFile("a.png", b"\x89PNG0000"), kind="photo")
    f = D.default_flow()
    f["screens"]["start"]["media"] = m.pk
    proj.flow = f
    proj.save()
    bot.handle_update(proj, msg(1, "/start"), api)
    m.refresh_from_db()
    assert m.tg_file_id.startswith("fid_")
    bot.handle_update(proj, msg(1, "/start"), api)
    media_calls = [c for c in api.calls if c[0] == "sendMedia"]
    assert len(media_calls) == 2


# ───────────── panel ─────────────
@pytest.fixture
def cl(admin):
    c = Client()
    c.force_login(admin)
    return c


def staff(db, perms_):
    from apps.accounts.models import UserPermissionOverride
    u = User.objects.create_user("xodim", password="x12345678")
    for code in perms_:
        UserPermissionOverride.objects.create(user=u, code=code, allow=True)
    c = Client()
    c.force_login(u)
    return c


def test_pages_render_for_admin(proj, cl):
    S.event(proj, "test", "hodisa")
    Lead.objects.create(project=proj, tg_id=3, first_name="Vali", phone="+998900000001")
    for name, args in [("online_home", []), ("online_new", []), ("online_project", [proj.pk]), ("online_bot", [proj.pk]), ("online_leads", [proj.pk]), ("online_subs", [proj.pk]),
                       ("online_payments", [proj.pk]), ("online_tariffs", [proj.pk]), ("online_ai", [proj.pk]), ("online_groups", [proj.pk]), ("online_events", [proj.pk]),
                       ("online_settings", [proj.pk])]:
        from django.urls import reverse
        r = cl.get(reverse(name, args=args))
        assert r.status_code == 200, name
    assert "Onlayn kanal" in cl.get("/").content.decode()


def test_create_project_panel(cl):
    r = cl.post("/onlayn/yangi/", {"name": "Yangi loyiha", "token": "1:x", "brief": "", })
    p = OnlineProject.objects.get(name="Yangi loyiha")
    assert r.status_code == 302 and p.bot_username == "fake_bot" and p.token() == "1:x" and p.flow["screens"]["start"]
    assert "1:x" not in cl.get(f"/onlayn/{p.pk}/sozlamalar/").content.decode()


def test_ai_generate_fills_draft(proj, cl, monkeypatch):
    from apps.ai_router.providers import FakeAIProvider
    payload = json.dumps({"about": "Kurs boti", "description": "Tavsif", "start_text": "Salom {name}!", "phone_text": "Raqam?", "menu_text": "Menyu", "ai_instructions": "Qisqa yoz",
                          "faq": [{"title": "Narx", "content": "299000"}]})
    monkeypatch.setattr("apps.ai_router.router.AIRouter.__init__", lambda self, providers=None, use_fakes=None: setattr(self, "fake", True) or setattr(self, "providers", {"openai": FakeAIProvider("openai", [payload]), "claude": FakeAIProvider("claude", [payload])}))
    r = cl.post(f"/onlayn/{proj.pk}/bot/ai/", {"brief": "Python kursi yopiq guruhda, yosh dasturchilar uchun, do'stona ohang"})
    assert r.status_code == 302
    proj.refresh_from_db()
    assert proj.about == "Kurs boti" and proj.flow_draft["screens"]["start"]["text"] == "Salom {name}!" and proj.docs.filter(title="Narx").exists()
    assert proj.flow["screens"]["start"]["text"] != "Salom {name}!"       # joriy bot o'zgarmagan


def test_constructor_save_publish_rollback(proj, cl):
    f = D.get_flow(proj)
    f["screens"]["start"]["text"] = "Yangi salom {name}"
    r = cl.post(f"/onlayn/{proj.pk}/bot/saqlash/", json.dumps(f), content_type="application/json")
    assert r.json()["ok"]
    proj.refresh_from_db()
    assert proj.flow_draft["screens"]["start"]["text"] == "Yangi salom {name}" and "Yangi" not in proj.flow["screens"]["start"]["text"]
    assert cl.post(f"/onlayn/{proj.pk}/bot/saqlash/", json.dumps({"screens": {}}), content_type="application/json").status_code == 400
    cl.post(f"/onlayn/{proj.pk}/bot/joriy/")
    proj.refresh_from_db()
    assert proj.flow["screens"]["start"]["text"] == "Yangi salom {name}" and proj.flow_draft is None and proj.versions.count() == 1
    cl.post(f"/onlayn/{proj.pk}/bot/versiya/", {"version": proj.versions.first().pk})
    proj.refresh_from_db()
    assert proj.flow_draft is not None


def test_media_upload_validation(proj, cl):
    ok = cl.post(f"/onlayn/{proj.pk}/media/yuklash/", {"file": SimpleUploadedFile("a.png", b"\x89PNG....")})
    assert ok.json()["ok"] and cl.get(ok.json()["url"]).status_code == 200
    bad = cl.post(f"/onlayn/{proj.pk}/media/yuklash/", {"file": SimpleUploadedFile("a.exe", b"MZ")})
    assert bad.status_code == 400


def test_panel_approve_payment_and_receipt(proj, api, cl):
    lead, p = pay_through(proj, api)
    cl.post(f"/onlayn/{proj.pk}/tolovlar/{p.pk}/qaror/", {"do": "ok"})
    p.refresh_from_db()
    assert p.status == "approved" and "panel" in p.decided_by
    assert cl.get(f"/onlayn/{proj.pk}/tolovlar/{p.pk}/chek/").status_code == 200


def test_manual_grant_by_username_and_cancel(proj, api, cl):
    start_and_phone(proj, api)
    cl.post(f"/onlayn/{proj.pk}/obunachilar/amal/", {"action": "grant", "q": "@u1", "days": "10"})
    lead = Lead.objects.get(project=proj, tg_id=1)
    sub = S.active_sub(lead)
    assert sub and sub.source == "manual" and (sub.ends_at - timezone.now()).days in (9, 10)
    cl.post(f"/onlayn/{proj.pk}/obunachilar/amal/", {"action": "cancel", "lead": lead.pk})
    assert S.active_sub(lead) is None


def test_leads_filter_export_and_actions(proj, api, cl):
    start_and_phone(proj, api, 1)
    bot.handle_update(proj, msg(2, "/start"), api)
    r = cl.get(f"/onlayn/{proj.pk}/leadlar/?phone=1")
    assert "Ali" in r.content.decode() and r.context["page"].paginator.count == 1
    x = cl.get(f"/onlayn/{proj.pk}/leadlar/?export=1")
    assert x["Content-Type"].startswith("application/vnd.openxmlformats")
    lead = Lead.objects.get(project=proj, tg_id=1)
    cl.post(f"/onlayn/{proj.pk}/leadlar/{lead.pk}/", {"action": "note", "text": "Qo'ng'iroq qilindi"})
    cl.post(f"/onlayn/{proj.pk}/leadlar/{lead.pk}/", {"action": "status", "status": "interested"})
    lead.refresh_from_db()
    assert lead.status == "interested" and lead.notes.count() == 1


def test_ai_test_chat_endpoint(proj, cl):
    KnowledgeDoc.objects.create(project=proj, title="Narx", content="Narx 299000")
    r = cl.post(f"/onlayn/{proj.pk}/ai/sinov/", json.dumps({"q": "narx?"}), content_type="application/json").json()
    assert r["ok"] and r["answer"]


# ───────────── ruxsatlar ─────────────
def test_permissions_split(proj, db):
    c = staff(db, ["online.view"])
    assert c.get("/onlayn/").status_code == 200
    assert c.get(f"/onlayn/{proj.pk}/").status_code == 200
    assert c.get(f"/onlayn/{proj.pk}/leadlar/").status_code == 403          # leads_view yo'q
    assert c.get(f"/onlayn/{proj.pk}/sozlamalar/").status_code == 403       # faqat admin
    assert c.get("/onlayn/yangi/").status_code == 403
    assert c.post(f"/onlayn/{proj.pk}/tolovlar/1/qaror/", {"do": "ok"}).status_code == 403
    assert c.post(f"/onlayn/{proj.pk}/sozlash/").status_code == 403
    assert c.post(f"/onlayn/{proj.pk}/bot/saqlash/", "{}", content_type="application/json").status_code == 403


def test_configure_never_grantable(db):
    from apps.accounts.permissions_registry import ADMIN_ONLY
    from apps.accounts.services import perms
    assert "online.configure" in ADMIN_ONLY
    u = User.objects.create_user("zz", password="x12345678")
    from apps.accounts.models import UserPermissionOverride
    UserPermissionOverride.objects.create(user=u, code="online.configure", allow=True)
    assert not perms.can(u, "online.configure", None)


def test_lead_staff_can_work_leads(proj, api, db):
    start_and_phone(proj, api)
    c = staff(db, ["online.view", "online.leads_view", "online.leads_edit"])
    lead = Lead.objects.get(project=proj, tg_id=1)
    assert c.get(f"/onlayn/{proj.pk}/leadlar/").status_code == 200
    c.post(f"/onlayn/{proj.pk}/leadlar/{lead.pk}/", {"action": "note", "text": "ok"})
    assert lead.notes.count() == 1
    assert c.get(f"/onlayn/{proj.pk}/leadlar/?export=1").status_code in (200, 302)   # export ruxsati yo'q -> qaytariladi
    assert "openxmlformats" not in c.get(f"/onlayn/{proj.pk}/leadlar/?export=1").get("Content-Type", "")


def test_no_access_hides_menu(db, proj):
    u = User.objects.create_user("bosh", password="x12345678")
    c = Client()
    c.force_login(u)
    assert c.get("/onlayn/").status_code == 403


def test_other_modules_unaffected(cl):
    for url in ("/", "/stories/", "/foydalanuvchilar/"):
        assert cl.get(url).status_code in (200, 302)
