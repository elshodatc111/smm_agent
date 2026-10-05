from datetime import timedelta

import pytest
from django.utils import timezone

from apps.connections.models import TelegramSession
from apps.connections.telethon_ro import (ALLOWED_METHODS, ReadOnlyViolation, SafetyGuard, SessionStopped,
                                         TelethonReadOnlyClient)
from apps.core import ratelimit
from apps.core.settings_store import set_setting


class FakeClient:
    def __init__(self):
        self.sent = []
    def get_messages(self, *a, **k): return ["m"]
    def send_message(self, *a, **k): self.sent.append(a)
    def iter_messages(self, *a, **k): return []


@pytest.fixture(autouse=True)
def nosleep(monkeypatch):
    monkeypatch.setattr(ratelimit, "SLEEP", lambda s: None)


@pytest.fixture
def sess(db, admin):
    set_setting("telethon.active_hours", ["00:00", "23:59"], user=admin)
    return TelegramSession.objects.create(name="s1", session_enc="x")


def client(sess):
    return TelethonReadOnlyClient(FakeClient(), SafetyGuard(sess), runner=lambda c: c)


def test_whitelist_blocks_dangerous_methods(sess):
    c = client(sess)
    for name in ("send_message", "join_channel", "delete_messages", "edit_message", "forward_messages", "__call__", "send_file", "invoke"):
        with pytest.raises(ReadOnlyViolation):
            getattr(c, name)
    assert c._client.sent == []
    assert "send_message" not in ALLOWED_METHODS


def test_allowed_method_counts(sess):
    c = client(sess)
    assert c.get_messages("x") == ["m"]
    sess.refresh_from_db()
    assert sess.requests_today == 1


def test_daily_cap_stops(sess, admin):
    set_setting("telethon.daily_request_cap", 2, user=admin)
    c = client(sess)
    c.get_messages("a"); c.get_messages("b")
    with pytest.raises(SessionStopped):
        c.get_messages("c")


def test_floodwait_cools_down(sess):
    class Flood(Exception):
        seconds = 120
    class Bad(FakeClient):
        def get_messages(self, *a, **k): raise Flood("flood")
    c = TelethonReadOnlyClient(Bad(), SafetyGuard(sess), runner=lambda x: x)
    with pytest.raises(Exception):
        c.get_messages("x")
    sess.refresh_from_db()
    assert sess.cooldown_until and sess.cooldown_until > timezone.now() + timedelta(seconds=120)
    with pytest.raises(SessionStopped):
        client(sess).get_messages("x")


def test_consecutive_errors_stop_session(sess):
    class Bad(FakeClient):
        def get_messages(self, *a, **k): raise RuntimeError("boom")
    c = TelethonReadOnlyClient(Bad(), SafetyGuard(sess), runner=lambda x: x)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            c.get_messages("x")
    sess.refresh_from_db()
    assert sess.cooldown_until > timezone.now() + timedelta(hours=5)


def test_outside_active_hours_blocked(sess, admin):
    set_setting("telethon.active_hours", ["03:00", "03:01"], user=admin)
    from apps.core.utils import local
    if "03:00" <= local(timezone.now()).strftime("%H:%M") <= "03:01":
        pytest.skip("vaqt oynasi mos tushdi")
    with pytest.raises(SessionStopped):
        client(sess).get_messages("x")


def test_no_send_code_in_module():
    import inspect
    from apps.connections import telethon_ro
    src = inspect.getsource(telethon_ro)
    for bad in ("send_message(", "JoinChannel", "ImportChatInvite", "delete_messages(", "send_file("):
        assert bad not in src
