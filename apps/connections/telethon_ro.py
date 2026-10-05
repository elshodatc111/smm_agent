"""Telethon — FAQAT O'QISH, ban xavfini kamaytiruvchi qatlam.

Qoidalar (CLAUDE.md §6.2):
 - faqat WHITELIST metodlar; yuborish/qo'shilish/o'chirish metodlari yo'q;
 - kunlik so'rov chegarasi, so'rovlar orasida tasodifiy tanaffus (jitter), faol soatlar;
 - FloodWait -> darhol to'xtash + sovitish; ketma-ket xatolar -> sessiya to'xtatiladi;
 - ulanish har yig'ish sessiyasida bir marta ochiladi (har so'rovda qayta kirish yo'q).
"""
from __future__ import annotations

import asyncio
import random
from datetime import timedelta

from django.utils import timezone

from apps.core import ratelimit
from apps.core.notify import notify
from apps.core.settings_store import get_secret, get_setting

from .base import PlatformError, RateLimitError

ALLOWED_METHODS = frozenset({"get_entity", "get_messages", "iter_messages", "get_stats", "get_participants_count"})


class ReadOnlyViolation(Exception):
    """Ruxsat etilmagan Telethon metodi chaqirildi."""


class SessionStopped(PlatformError):
    code = "telethon_stopped"
    user_message_uz = "Telegram akkaunti xavfsizlik uchun vaqtincha to'xtatildi."


class SafetyGuard:
    """DB dagi TelegramSession hisoblagichlari ustida ishlaydi (testlanadigan mantiq)."""

    def __init__(self, session_row, now=None):
        self.s = session_row
        self.now = now or timezone.now

    def _local_hhmm(self):
        from apps.core.utils import local
        return local(self.now()).strftime("%H:%M")

    def check(self) -> None:
        s, now = self.s, self.now()
        if not s.active:
            raise SessionStopped("sessiya o'chirilgan")
        if s.cooldown_until and s.cooldown_until > now:
            raise SessionStopped(f"sovitish tugaguncha: {s.cooldown_until}")
        start, end = get_setting("telethon.active_hours", ["00:00", "23:59"])
        if not (start <= self._local_hhmm() <= end):
            raise SessionStopped("faol soatlardan tashqari")
        if s.day != now.date():
            s.day, s.requests_today = now.date(), 0
        if s.requests_today >= int(get_setting("telethon.daily_request_cap", 400)):
            raise SessionStopped("kunlik so'rov chegarasi tugadi")

    def pause(self) -> float:
        lo = float(get_setting("telethon.min_delay_sec", 3))
        hi = float(get_setting("telethon.max_delay_sec", 9))
        ratelimit.throttle(f"telethon:{self.s.pk}", lo, max(0.0, hi - lo))
        return lo

    def record_ok(self) -> None:
        s = self.s
        s.requests_today += 1
        s.consecutive_errors = 0
        s.last_request_at = self.now()
        s.save(update_fields=["requests_today", "day", "consecutive_errors", "last_request_at"])

    def record_error(self, msg: str, flood_seconds: int | None = None) -> None:
        s = self.s
        s.consecutive_errors += 1
        s.last_error = msg[:300]
        if flood_seconds:
            s.cooldown_until = self.now() + timedelta(seconds=flood_seconds + random.randint(60, 300))
            notify("quota.warning", "Telegram akkaunti: FloodWait",
                   f"{flood_seconds} soniya kutish talab qilindi, sessiya sovitildi.", severity="warn",
                   dedupe_key=f"flood:{s.pk}")
        if s.consecutive_errors >= int(get_setting("telethon.max_consecutive_errors", 3)):
            s.cooldown_until = self.now() + timedelta(hours=6)
            notify("connection.error", "Telegram akkaunti to'xtatildi",
                   "Ketma-ket xatolar: ban oldini olish uchun 6 soatga to'xtatildi.", severity="critical",
                   dedupe_key=f"tg-stop:{s.pk}")
        s.save()


class TelethonReadOnlyClient:
    """Whitelist wrapper. client — telethon.TelegramClient (yoki testda soxta obyekt)."""

    def __init__(self, client, guard: SafetyGuard, runner=None):
        self._client = client
        self._guard = guard
        self._run = runner or (lambda coro: asyncio.get_event_loop().run_until_complete(coro))

    def __getattr__(self, name: str):
        if name not in ALLOWED_METHODS:
            raise ReadOnlyViolation(f"'{name}' taqiqlangan: Telethon akkaunti faqat o'qish uchun.")
        target = getattr(self._client, name)

        def call(*a, **kw):
            self._guard.check()
            self._guard.pause()
            try:
                res = target(*a, **kw)
                if asyncio.iscoroutine(res):
                    res = self._run(res)
                self._guard.record_ok()
                return res
            except Exception as e:  # noqa: BLE001
                secs = getattr(e, "seconds", None)  # telethon FloodWaitError.seconds
                self._guard.record_error(f"{type(e).__name__}: {e}", flood_seconds=secs)
                if secs:
                    raise RateLimitError(f"FloodWait {secs}s", retry_after=secs) from e
                raise
        return call


def open_client(session_row):
    """Haqiqiy Telethon ulanishi. Telethon o'rnatilmagan bo'lsa tushunarli xato."""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError as e:  # pragma: no cover
        raise PlatformError("Telethon o'rnatilmagan: pip install telethon", user_message_uz="Telethon o'rnatilmagan.") from e
    api_id, api_hash = get_setting("telegram.api_id", ""), get_secret("telegram.api_hash")
    if not api_id or not api_hash:
        raise PlatformError("telegram.api_id/api_hash yo'q", user_message_uz="Sozlamalarda Telegram API ID/Hash kiritilmagan.")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TelegramClient(StringSession(session_row.string_session()), int(api_id), api_hash,
                            device_model="Desktop", system_version="Windows 10", app_version="5.0")
    loop.run_until_complete(client.connect())
    guard = SafetyGuard(session_row)
    return TelethonReadOnlyClient(client, guard, runner=loop.run_until_complete), client, loop
