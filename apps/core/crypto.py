"""Fernet shifrlash (MultiFernet: kalit aylantirish uchun)."""
import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


class CryptoError(Exception):
    pass


def _fernet() -> MultiFernet:
    keys = settings.FERNET_KEYS
    if not keys:
        raise CryptoError("FERNET_KEYS .env faylida topilmadi")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise CryptoError("Shifrni ochib bo'lmadi (FERNET_KEYS o'zgargan bo'lishi mumkin)") from e


def encrypt_json(obj) -> str:
    return encrypt(json.dumps(obj, ensure_ascii=False))


def decrypt_json(token: str):
    return json.loads(decrypt(token)) if token else None


def rotate(token: str) -> str:
    """Eski kalit bilan shifrlangan qiymatni birinchi (yangi) kalitga o'tkazadi."""
    return _fernet().rotate(token.encode("ascii")).decode("ascii")


def mask(value: str, tail: int = 4) -> str:
    if not value:
        return ""
    return "••••" + value[-tail:] if len(value) > tail else "••••"
