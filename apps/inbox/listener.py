"""Telethon tinglovchisi (worker ichidagi bitta oqim): har faol akkaunt uchun kiruvchi shaxsiy xabarlarni oladi,
operator Telegram ilovasidan yozganini aniqlaydi, AI javoblarini sekin va xavfsiz (yozmoqda... kechikishi, limitlar) yuboradi.
Mijozga HECH QACHON birinchi bo'lib yozmaydi: faqat mavjud suhbatdagi (mijoz yozgan) xabarlarga javob beradi."""
from __future__ import annotations

import asyncio
import logging
import random

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from apps.core.settings_store import get_secret, get_setting

from . import services as svc
from .models import InboxAccount

log = logging.getLogger(__name__)
TICK_SEC = 5


async def _db(fn, *a, **kw):
    """Django ORM chaqiruvini alohida oqimda bajaradi."""
    loop = asyncio.get_running_loop()

    def run():
        try:
            return fn(*a, **kw)
        finally:
            close_old_connections()
    return await loop.run_in_executor(None, run)


def _client(session_str: str):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    api_id, api_hash = get_setting("telegram.api_id", ""), get_secret("telegram.api_hash")
    if not api_id or not api_hash:
        raise RuntimeError("Telegram API ID/Hash sozlanmagan")
    return TelegramClient(StringSession(session_str), int(api_id), api_hash, device_model="Desktop", system_version="Windows 10", app_version="5.0")


async def _run_account(acc_id: int, stop: asyncio.Event):
    from datetime import timedelta

    from telethon import events
    from telethon.errors import FloodWaitError
    acc = await _db(InboxAccount.objects.get, pk=acc_id)
    client = await _db(lambda: _client(acc.string_session()))
    await client.connect()
    try:
        if not await client.is_user_authorized():
            await _db(InboxAccount.objects.filter(pk=acc_id).update, last_error="Sessiya eskirgan: qaytadan ulang", active=False)
            return
        me = await client.get_me()
        await _db(InboxAccount.objects.filter(pk=acc_id).update, tg_user_id=me.id, connected_at=timezone.now(), last_error="")

        @client.on(events.NewMessage(incoming=True))
        async def on_in(e):
            if not e.is_private:
                return
            s = await e.get_sender()
            if s is None or getattr(s, "bot", False) or s.id == me.id:
                return
            name = " ".join(x for x in (getattr(s, "first_name", ""), getattr(s, "last_name", "")) if x)
            await _db(svc.ingest_inbound, await _db(InboxAccount.objects.get, pk=acc_id), s.id, e.raw_text or ("[fayl/rasm]" if e.media else ""),
                      name=name, username=getattr(s, "username", "") or "", tg_msg_id=e.id, when=e.date)

        @client.on(events.NewMessage(outgoing=True))
        async def on_out(e):
            if not e.is_private:
                return
            await _db(svc.ingest_outgoing_human, await _db(InboxAccount.objects.get, pk=acc_id), e.chat_id, e.raw_text or "", tg_msg_id=e.id, when=e.date)

        while not stop.is_set():
            a = await _db(InboxAccount.objects.get, pk=acc_id)
            if not a.active:
                return
            try:
                await _db(svc.process_account, a)
                for pk, peer_id, text in await _db(svc.pending_for, a, 3):
                    try:
                        ent = await client.get_input_entity(peer_id)
                        async with client.action(ent, "typing"):
                            await asyncio.sleep(random.uniform(3, 8))
                        m = await client.send_message(ent, text)
                        await _db(svc.mark_sent, pk, m.id)
                    except FloodWaitError as fw:
                        await _db(svc.mark_failed, pk, f"FloodWait {fw.seconds}s")
                        await _db(InboxAccount.objects.filter(pk=acc_id).update, cooldown_until=timezone.now() + timedelta(seconds=fw.seconds + 60),
                                  last_error=f"Telegram cheklovi: {fw.seconds}s kutish")
                        return
                    except Exception as ex:  # noqa: BLE001
                        await _db(svc.mark_failed, pk, str(ex))
                    await asyncio.sleep(random.uniform(2, 5))
            except Exception:  # noqa: BLE001
                log.exception("inbox akkaunt tsikli xatosi (%s)", acc_id)
            try:
                await asyncio.wait_for(stop.wait(), timeout=TICK_SEC)
            except asyncio.TimeoutError:
                pass
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass


async def _main(stop_event):
    stop = asyncio.Event()
    tasks: dict[int, asyncio.Task] = {}
    while not stop_event.is_set():
        accounts = await _db(lambda: list(InboxAccount.objects.filter(active=True).exclude(session_enc="").exclude(cooldown_until__gt=timezone.now()).values_list("pk", flat=True)))
        for pk in accounts:
            t = tasks.get(pk)
            if t is None or t.done():
                if t is not None and not t.cancelled() and t.exception():
                    log.warning("inbox akkaunt %s to'xtadi: %s", pk, t.exception())
                tasks[pk] = asyncio.create_task(_run_account(pk, stop))
        for pk in list(tasks):
            if pk not in accounts and not tasks[pk].done():
                tasks[pk].cancel()
        await asyncio.sleep(20)
    stop.set()
    await asyncio.gather(*tasks.values(), return_exceptions=True)


def run_inbox_loop(stop_event) -> None:
    """Worker oqimi. Telethon o'rnatilmagan yoki sozlanmagan bo'lsa jim kutadi."""
    if settings.USE_FAKES:
        return
    while not stop_event.is_set():
        try:
            import telethon  # noqa: F401
            if not get_setting("telegram.api_id", "") or not get_secret("telegram.api_hash"):
                stop_event.wait(60)
                continue
            asyncio.run(_main(stop_event))
        except ImportError:
            log.warning("inbox: telethon o'rnatilmagan")
            stop_event.wait(300)
        except Exception:  # noqa: BLE001
            log.exception("inbox listener xatosi")
            stop_event.wait(15)
