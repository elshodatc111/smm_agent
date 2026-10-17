"""Murojaatlar: 15 daqiqalik kutish, skript asosidagi AI javobi, operatorga uzatish, jurnal, skriptning o'sishi, ruxsatlar."""
import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Role, User, UserBusinessAccess
from apps.ai_router.providers import FakeAIProvider
from apps.ai_router.router import AIRouter
from apps.core import crypto
from apps.inbox import services as svc
from apps.inbox.models import AIReplyLog, Conversation, InboxAccount, Message, ScriptEntry, ScriptGap


def router(*script):
    return AIRouter(providers={n: FakeAIProvider(n, list(script) if n == "openai" else []) for n in ("openai", "claude")}, use_fakes=True)


def ai(answer="", handoff=False, reason="", used=None, missing="", needs_operator=False):
    return json.dumps({"answer": answer, "handoff": handoff, "reason": reason, "used": used or [], "missing_question": missing, "needs_operator": needs_operator})


@pytest.fixture
def acc(biz):
    return InboxAccount.objects.create(business=biz, name="Operator-1", phone="+998", session_enc=crypto.encrypt("fake"), wait_minutes=15)


@pytest.fixture
def script(biz):
    return ScriptEntry.objects.create(business=biz, kind="qa", title="Kurs narxi", questions="narxi qancha\nkurs qancha turadi", answer="Kurs narxi 500000 so'm, 3 oy davom etadi.")


T0 = timezone.now() - timedelta(hours=2)


def inbound(acc, text="Kurs narxi qancha?", peer=111, when=T0, mid=None):
    return svc.ingest_inbound(acc, peer, text, name="Ali", username="ali", tg_msg_id=mid, when=when)


# ------------------------------------------------------------------ qabul qilish
def test_inbound_creates_conversation_and_dedupes(acc):
    m1 = inbound(acc, mid=5)
    m2 = inbound(acc, mid=5)
    assert m1.pk == m2.pk and Conversation.objects.count() == 1 and Message.objects.count() == 1
    c = Conversation.objects.get()
    assert c.business_id == acc.business_id and c.peer_name == "Ali" and c.unread


def test_never_initiates_conversation(acc):
    # operator mijozga o'zi birinchi yozgan bo'lsa — kuzatilmaydi, AI hech narsa yubormaydi
    assert svc.ingest_outgoing_human(acc, 999, "Salom", tg_msg_id=1) is None
    assert Conversation.objects.count() == 0 and svc.due_conversations(acc) == []


# ------------------------------------------------------------------ kutish va AI qo'shilishi
def test_ai_waits_for_operator_then_answers_with_disclosure(acc, script):
    inbound(acc, when=timezone.now() - timedelta(minutes=5))
    c = Conversation.objects.get()
    assert svc.due_conversations(acc) == []                                  # hali 15 daqiqa o'tmagan
    assert svc.auto_reply(c, router=router(ai("x")))["decision"] == "skipped"
    # 20 daqiqa o'tgan
    Message.objects.update(created_at=timezone.now() - timedelta(minutes=20))
    Conversation.objects.update(last_inbound_at=timezone.now() - timedelta(minutes=20))
    assert [x.pk for x in svc.due_conversations(acc)] == [c.pk]
    r = svc.auto_reply(c, router=router(ai("Kurs narxi 500000 so'm.", used=[script.pk])))
    assert r["decision"] == "answered"
    out = Message.objects.filter(direction="out").get()
    assert out.sender == "ai" and out.state == "pending" and "AI yordamchiman" in out.text and "500000" in out.text
    c.refresh_from_db()
    assert c.ai_disclosed
    log = AIReplyLog.objects.get()
    assert log.decision == "answered" and log.script_ids == [script.pk] and log.provider
    script.refresh_from_db()
    assert script.uses == 1


def test_operator_reply_in_time_blocks_ai(acc, script):
    inbound(acc, when=timezone.now() - timedelta(minutes=30))
    c = Conversation.objects.get()
    svc.queue_outbound(c, "Salom, hozir yozaman", sender="operator")
    assert svc.awaiting_message(c) is None and svc.due_conversations(acc) == []
    assert svc.auto_reply(c, router=router(ai("x")))["decision"] == "skipped"


def test_operator_reply_from_phone_app_counts(acc, script):
    inbound(acc, when=timezone.now() - timedelta(minutes=30))
    c = Conversation.objects.get()
    assert svc.ingest_outgoing_human(acc, 111, "Men javob beraman", tg_msg_id=77) is not None
    assert svc.awaiting_message(c) is None
    # tizim o'zi yuborgan xabarning hodisasi operator javobi hisoblanmaydi
    svc.queue_outbound(c, "AI matni", sender="ai")
    assert svc.ingest_outgoing_human(acc, 111, "AI matni", tg_msg_id=78) is None


def test_new_inbound_after_ai_answers_in_30s_not_15min(acc, script):
    inbound(acc, when=timezone.now() - timedelta(minutes=40))
    c = Conversation.objects.get()
    svc.auto_reply(c, router=router(ai("Kurs narxi 500000 so'm.")))
    Message.objects.filter(sender="ai").update(created_at=timezone.now() - timedelta(minutes=35))
    inbound(acc, "Necha oy davom etadi?", mid=9, when=timezone.now() - timedelta(minutes=2))
    assert [x.pk for x in svc.due_conversations(acc)] == [c.pk]      # AI rejimi: 15 daqiqa emas, 30 soniya


# ------------------------------------------------------------------ himoyalar
def test_missing_info_is_soft_flag_and_ai_keeps_answering(acc):
    inbound(acc, "Sizda ingliz tili kursi bormi?")
    c = Conversation.objects.get()
    r = svc.auto_reply(c, router=router(ai("Ha, kurslarimiz bor. Aniq jadvalni menejerimiz tasdiqlaydi. Ismingizni yozing.", needs_operator=True, missing="kurs jadvali")))
    assert r["decision"] == "answered"
    c.refresh_from_db()
    assert c.needs_human and not svc.is_hard(c) and c.human_reason.startswith(svc.SOFT)
    assert ScriptGap.objects.filter(business=acc.business, status="new").exists()
    # yumshoq belgidan keyin ham AI keyingi savolga javob beradi (to'xtab qolmaydi)
    Message.objects.filter(sender="ai").update(created_at=timezone.now() - timedelta(minutes=35))
    inbound(acc, "Narxi qancha?", mid=77, when=timezone.now() - timedelta(minutes=2))
    assert [x.pk for x in svc.due_conversations(acc)] == [c.pk]
    assert svc.auto_reply(c, router=router(ai("Narx 500000 so'mdan.")))["decision"] == "answered"


def test_smalltalk_is_answered_not_handed_off(acc, script):
    inbound(acc, "Sani yoshing nechi")
    c = Conversation.objects.get()
    r = svc.auto_reply(c, router=router(ai("Men AI yordamchiman, yoshim yo'q. Kurslar haqida savolingiz bormi?")))
    assert r["decision"] == "answered"
    c.refresh_from_db()
    assert not c.needs_human


def test_ai_unavailable_three_times_hands_off(acc, script):
    from apps.ai_router.router import AIUnavailable
    inbound(acc)
    c = Conversation.objects.get()
    for _ in range(3):
        r = svc.auto_reply(c, router=AIRouter(providers={}, use_fakes=False))
    assert r["decision"] == "handoff" and svc.is_hard(Conversation.objects.get())


def test_handoff_keywords_never_reach_ai(acc, script):
    inbound(acc, "Shikoyatim bor, pulni qaytaring!")
    c = Conversation.objects.get()
    r = svc.auto_reply(c, router=router(ai("Hammasi yaxshi")))
    assert r["decision"] == "handoff" and "ehtiyotkor" in r["reason"]
    assert AIReplyLog.objects.get().decision == "handoff"


def test_ai_says_handoff_records_gap(acc, script):
    inbound(acc, "Kechki guruh bormi?")
    c = Conversation.objects.get()
    r = svc.auto_reply(c, router=router(ai("", handoff=True, reason="skriptda yo'q", missing="Kechki guruh bormi?")))
    assert r["decision"] == "handoff"
    assert ScriptGap.objects.get().question.startswith("Kechki guruh")


def test_invented_price_is_blocked(acc, script):
    inbound(acc, "Narxi qancha?")
    c = Conversation.objects.get()
    r = svc.auto_reply(c, router=router(ai("Kurs narxi 350000 so'm.", used=[script.pk])))
    assert r["decision"] == "answered"
    assert not any("350000" in m.text for m in Message.objects.filter(direction="out"))
    assert Conversation.objects.get().needs_human and not svc.is_hard(Conversation.objects.get())


def test_hourly_limit_and_streak(acc, script):
    acc.hourly_limit = 1
    acc.save()
    inbound(acc, "Narxi qancha?")
    c = Conversation.objects.get()
    Message.objects.create(conversation=c, direction="out", sender="ai", text="eski", state="sent", created_at=timezone.now() - timedelta(minutes=40))
    inbound(acc, "Yana narx?", mid=3, when=timezone.now() - timedelta(minutes=20))
    assert svc.auto_reply(c, router=router(ai("Kurs narxi 500000 so'm.")))["reason"] == "soatlik limit"


def test_auto_reply_off_or_ai_disabled(acc, script):
    inbound(acc)
    c = Conversation.objects.get()
    acc.auto_reply = False
    acc.save()
    assert svc.due_conversations(acc) == []
    acc.auto_reply = True
    acc.save()
    c.ai_enabled = False
    c.save()
    assert svc.due_conversations(acc) == []


def test_ai_unavailable_is_logged_not_crashing(acc, script):
    inbound(acc)
    c = Conversation.objects.get()
    r = svc.auto_reply(c, router=AIRouter(providers={}, use_fakes=False))
    assert r["decision"] == "failed" and AIReplyLog.objects.get().decision == "failed"


# ------------------------------------------------------------------ yuborish navbati
def test_flush_pending_marks_sent_and_failed(acc):
    inbound(acc)
    c = Conversation.objects.get()
    a = svc.queue_outbound(c, "bir", sender="operator")
    b = svc.queue_outbound(c, "ikki", sender="ai")
    seen = []

    def send(peer, text):
        seen.append((peer, text))
        if text == "ikki":
            raise RuntimeError("tarmoq")
        return 4242
    assert svc.flush_pending(acc, send) == 1
    a.refresh_from_db(); b.refresh_from_db()
    assert a.state == "sent" and a.tg_msg_id == 4242 and b.state == "failed" and "tarmoq" in b.error and seen[0][0] == 111


# ------------------------------------------------------------------ operatorga yordam va skript o'sishi
def test_suggest_replies_and_learn_from_operator(acc, script, admin):
    inbound(acc, "Dars soat nechada?")
    c = Conversation.objects.get()
    opts = svc.suggest_replies(c, admin, router(json.dumps({"options": [{"label": "Qisqa", "text": "10:00 da"}, {"label": "Batafsil", "text": "Dars 10:00 da boshlanadi"}]})))
    assert len(opts) == 2 and opts[0]["text"] == "10:00 da"
    svc.record_gap(acc.business, "Dars soat nechada?", c)
    m = svc.queue_outbound(c, "Darslar 10:00 da boshlanadi.", sender="operator", user=admin)
    e = svc.add_to_script(c, m, admin)
    assert e and e.source == "learned" and "10:00" in e.answer and e.questions.startswith("Dars soat")
    assert ScriptGap.objects.get().status == "added"
    assert svc.add_to_script(c, Message.objects.filter(direction="in").first(), admin) is None


# ------------------------------------------------------------------ veb va ruxsatlar
def client_for(user, pw, biz=None):
    c = Client()
    assert c.post("/kirish/", {"username": user.username, "password": pw}).status_code == 302
    if biz:
        c.post("/biznes-tanlash/", {"business": biz.pk})
    return c


@pytest.fixture
def boss(db):
    return User.objects.create_user("boss", password="Boss#2026test!", is_admin=True)


def test_pages_render_and_reply_flow(acc, script, boss, biz):
    inbound(acc)
    c = Conversation.objects.get()
    cl = client_for(boss, "Boss#2026test!", biz)
    for u in ("/murojaatlar/", "/murojaatlar/akkauntlar/", "/murojaatlar/skript/", "/murojaatlar/jurnal/", f"/murojaatlar/{c.pk}/", "/murojaatlar/?tab=human"):
        assert cl.get(u).status_code == 200, u
    assert "Ali" in cl.get("/murojaatlar/").content.decode()
    assert cl.post(f"/murojaatlar/{c.pk}/javob/", {"text": "Salom, yozing"}).status_code == 302
    assert Message.objects.filter(sender="operator", state="pending", by_user=boss).exists()
    assert cl.post(f"/murojaatlar/{c.pk}/ai/").status_code == 302
    c.refresh_from_db()
    assert not c.ai_enabled
    assert cl.post(f"/murojaatlar/{c.pk}/taklif/").status_code == 302
    r = cl.post("/murojaatlar/skript/saqlash/", {"business": biz.pk, "kind": "qa", "title": "Manzil", "questions": "qayerda", "answer": "Toshkent, Chilonzor"})
    assert r.status_code == 302 and ScriptEntry.objects.filter(title="Manzil").exists()
    assert cl.post("/murojaatlar/akkauntlar/qoshish/", {"business": biz.pk, "name": "Op2", "phone": "+9989"}).status_code == 302
    assert InboxAccount.objects.filter(name="Op2").exists()


def test_isolation_between_businesses_and_rbac(acc, script, biz, biz2):
    inbound(acc)
    c = Conversation.objects.get()
    role = Role.objects.get(name="Menejer")
    u = User.objects.create_user("men", password="Men#2026test!")
    UserBusinessAccess.objects.create(user=u, business=biz2, role=role)
    from apps.accounts.services import bump_permissions
    bump_permissions()
    cl = client_for(u, "Men#2026test!", biz2)
    assert cl.get(f"/murojaatlar/{c.pk}/").status_code == 404
    assert cl.post(f"/murojaatlar/{c.pk}/javob/", {"text": "x"}).status_code == 404
    assert "Ali" not in cl.get("/murojaatlar/").content.decode()
    # ruxsatsiz rol
    role2 = Role.objects.get(name="Kontent-maker")
    u2 = User.objects.create_user("km", password="Km#2026test!")
    UserBusinessAccess.objects.create(user=u2, business=biz, role=role2)
    bump_permissions()
    cl2 = client_for(u2, "Km#2026test!", biz)
    assert cl2.get("/murojaatlar/").status_code in (302, 403)


def test_disclosure_uses_ai_name():
    from apps.inbox.services import DISCLOSURE, disclosure

    class A:  # noqa: D401
        ai_name = "Alisa"
    assert "Men AI Alisaman" in disclosure(A()) and "operator emasman" in disclosure(A())
    A.ai_name = ""
    assert disclosure(A()) == DISCLOSURE


# ------------------------------------------------------------------ AI rejimi (davomiy javoblar)
def _ai_out(conv, ago_min):
    conv.ai_disclosed = True
    conv.save(update_fields=["ai_disclosed"])
    return Message.objects.create(conversation=conv, direction="out", sender="ai", text="Javob", state="sent",
                                  created_at=timezone.now() - timedelta(minutes=ago_min))


def test_followup_in_ai_mode_waits_only_30_seconds(acc, script):
    now = timezone.now()
    inbound(acc, "Birinchi savol", when=now - timedelta(minutes=10))
    c = Conversation.objects.get()
    _ai_out(c, 9)
    inbound(acc, "Kurs narxi qancha?", when=now - timedelta(seconds=10), mid=2)
    assert svc.ai_mode(c)
    assert svc.due_conversations(acc) == []                                   # 10 soniya — hali erta
    assert svc.auto_reply(c, router=router(ai("x")))["decision"] == "skipped"
    Message.objects.filter(direction="in").update(created_at=now - timedelta(seconds=40))
    Conversation.objects.update(last_inbound_at=now - timedelta(seconds=40))
    assert [x.pk for x in svc.due_conversations(acc)] == [c.pk]
    r = svc.auto_reply(c, router=router(ai("Kurs narxi 500000 so'm.", used=[script.pk])))
    assert r["decision"] == "answered"
    out = Message.objects.filter(direction="out", sender="ai", state="pending").get()
    assert "AI yordamchiman" not in out.text and "500000" in out.text        # tanishtiruv qaytarilmaydi (ai_disclosed hali False bo'lsa ham)


def test_ai_mode_debounces_burst_of_messages(acc):
    now = timezone.now()
    inbound(acc, "Salom", when=now - timedelta(minutes=10))
    c = Conversation.objects.get()
    _ai_out(c, 9)
    inbound(acc, "narxi", when=now - timedelta(seconds=50), mid=2)
    inbound(acc, "qancha?", when=now - timedelta(seconds=10), mid=3)
    # oxirgi xabardan 30 soniya o'tmagan — birinchisidan 50 soniya o'tgan bo'lsa ham kutadi
    assert svc.due_conversations(acc) == []


def test_ai_mode_expires_back_to_operator_wait(acc):
    now = timezone.now()
    inbound(acc, "Salom", when=now - timedelta(hours=6))
    c = Conversation.objects.get()
    _ai_out(c, 5 * 60)                                                       # 5 soat oldin — sessiya (3 soat) tugagan
    inbound(acc, "Yana savol", when=now - timedelta(minutes=2), mid=2)
    assert not svc.ai_mode(c)
    assert svc.due_conversations(acc) == []                                   # operatorga yana wait_minutes beriladi
    acc.ai_session_minutes = 600
    acc.save()
    c.refresh_from_db()
    assert svc.ai_mode(c)


def test_operator_reply_returns_to_operator_wait(acc):
    now = timezone.now()
    inbound(acc, "Salom", when=now - timedelta(minutes=10))
    c = Conversation.objects.get()
    _ai_out(c, 9)
    Message.objects.create(conversation=c, direction="out", sender="operator", text="Salom, men operator", state="sent", created_at=now - timedelta(minutes=5))
    inbound(acc, "Narxi?", when=now - timedelta(minutes=2), mid=2)
    assert not svc.ai_mode(c)
    assert svc.due_conversations(acc) == []                                   # 2 daqiqa < 15


def test_strip_greeting_after_disclosure():
    from apps.inbox.services import strip_greeting
    assert strip_greeting("Assalomu alaykum! ATKO 2017-yildan beri.") == "ATKO 2017-yildan beri."
    assert strip_greeting("Salom, kurs narxi 500 000.") == "Kurs narxi 500 000."
    assert strip_greeting("Narx 500 000.") == "Narx 500 000."


def test_inbox_home_live_countdown(db, settings):
    from django.test import Client
    from apps.accounts.models import User
    u = User.objects.create_user("lv", password="x12345678", is_admin=True)
    c = Client(); c.force_login(u)
    html = c.get("/murojaatlar/").content.decode()
    assert 'data-live="root"' in html and "setInterval(poll" in html
