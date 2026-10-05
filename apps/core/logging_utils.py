import logging
import re

_PATTERNS = [
    re.compile(r"(bot)(\d{6,}:[A-Za-z0-9_-]{30,})"),
    re.compile(r"(?i)(access_token|refresh_token|client_secret|api_key|key|token|password|authorization)(['\"]?\s*[:=]\s*['\"]?)([A-Za-z0-9._\-~+/]{8,})"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"gsk_[0-9A-Za-z]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"EA[A-Za-z0-9]{40,}"),
    re.compile(r"IG[A-Za-z0-9_\-]{40,}"),
]


def scrub(text: str) -> str:
    """Matndagi token/kalit/parolga o'xshash qiymatlarni niqoblaydi."""
    if not text:
        return text
    text = re.sub(r"(?i)(bearer\s+|oauth\s+)[A-Za-z0-9._\-~+/=]{8,}", r"\1••••", text)
    text = _PATTERNS[0].sub(r"\1••••", text)
    text = _PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}••••", text)
    for p in _PATTERNS[2:]:
        text = p.sub("••••", text)
    return text


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = scrub(record.getMessage())
            record.args = ()
        except Exception:  # noqa: BLE001
            pass
        return True
