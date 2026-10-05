"""Telethon sessiyasini veb-interfeys orqali olish (telefon -> kod -> [2FA parol]). Faqat o'qish uchun ishlatiladi."""
from __future__ import annotations

import asyncio

from apps.core.settings_store import get_secret, get_setting

from .base import PlatformError


def _mk(session_str: str = ""):
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError as e:  # pragma: no cover
        raise PlatformError("telethon yo'q", user_message_uz="Telethon o'rnatilmagan (pip install telethon).") from e
    api_id, api_hash = get_setting("telegram.api_id", ""), get_secret("telegram.api_hash")
    if not api_id or not api_hash:
        raise PlatformError("api_id yo'q", user_message_uz="Avval Sozlamalar → Telegram bo'limida API ID va API Hash kiriting.")
    loop = asyncio.new_event_loop()
    client = TelegramClient(StringSession(session_str), int(api_id), api_hash, device_model="Desktop", system_version="Windows 10", app_version="5.0", loop=loop)
    return client, loop


def _close(client, loop) -> None:
    """Telethon 1.x da disconnect() halqa ishlamayotganda o'zi bajaradi va None qaytaradi — shuning uchun tekshiramiz."""
    try:
        r = client.disconnect()
        if r is not None and asyncio.iscoroutine(r) or isinstance(r, asyncio.Future):
            loop.run_until_complete(r)
    except Exception:  # noqa: BLE001
        pass
    finally:
        loop.close()


def send_code(phone: str) -> dict:
    client, loop = _mk()
    try:
        loop.run_until_complete(client.connect())
        sent = loop.run_until_complete(client.send_code_request(phone))
        return {"session": client.session.save(), "hash": sent.phone_code_hash}
    finally:
        _close(client, loop)


def sign_in(phone: str, session: str, code_hash: str, code: str = "", password: str = "") -> dict:
    """{'ok': True, 'session': str} | {'need_password': True, 'session': str}"""
    from telethon.errors import SessionPasswordNeededError
    client, loop = _mk(session)
    try:
        loop.run_until_complete(client.connect())
        try:
            if password:
                loop.run_until_complete(client.sign_in(password=password))
            else:
                loop.run_until_complete(client.sign_in(phone=phone, code=code, phone_code_hash=code_hash))
        except SessionPasswordNeededError:
            return {"need_password": True, "session": client.session.save()}
        return {"ok": True, "session": client.session.save()}
    finally:
        _close(client, loop)
