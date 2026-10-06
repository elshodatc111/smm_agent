"""Post matni uchun HTML teglar: Telegram'da formatlash, boshqa platformalarda toza matn.

Telegram Bot API (parse_mode=HTML) faqat cheklangan teglarni tushunadi. Foydalanuvchi yozgan matn
nashrdan oldin shu yerdan o'tadi: ruxsat etilgan teglar saqlanadi, noto'g'ri/ortiqcha teglar
va yakka `<`, `&` belgilari xavfsiz tarzda «escape» qilinadi (aks holda Telegram xato qaytaradi).
"""
from __future__ import annotations

import html
import re

# Telegram qo'llab-quvvatlaydigan teglar
ALLOWED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "blockquote", "tg-spoiler", "a"}
_TAG = re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:\s[^<>]*)?)/?>")
_ENTITY = re.compile(r"&(?:amp|lt|gt|quot|#\d{1,7}|#x[0-9a-fA-F]{1,6});")
_HREF = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.I)
_LANG = re.compile(r"""class\s*=\s*["']?(language-[\w+#.-]{1,30})["']?""", re.I)
_SAFE_URL = ("http://", "https://", "tg://", "mailto:")


def _esc_text(s: str) -> str:
    """Oddiy matn bo'lagi: `&` (agar to'g'ri entity bo'lmasa), `<`, `>` ni escape qiladi."""
    out, pos = [], 0
    for m in _ENTITY.finditer(s):
        out.append(s[pos:m.start()].replace("&", "&amp;"))
        out.append(m.group(0))
        pos = m.end()
    out.append(s[pos:].replace("&", "&amp;"))
    return "".join(out).replace("<", "&lt;").replace(">", "&gt;")


def _open_tag(name: str, attrs: str) -> tuple[str, str] | None:
    """(kanonik nom, tayyor ochuvchi teg) yoki None (teg ruxsat etilmagan)."""
    if name == "span":
        if "tg-spoiler" in attrs.lower():
            return "tg-spoiler", "<tg-spoiler>"
        return None
    if name not in ALLOWED:
        return None
    if name == "a":
        m = _HREF.search(attrs)
        url = html.unescape((m.group(1) or m.group(2) or m.group(3) or "") if m else "").strip()
        if not url.lower().startswith(_SAFE_URL):
            return None
        return "a", f'<a href="{html.escape(url, quote=True)}">'
    if name == "code":
        m = _LANG.search(attrs)
        return "code", f'<code class="{m.group(1)}">' if m else "<code>"
    if name == "blockquote":
        return "blockquote", "<blockquote expandable>" if re.search(r"\bexpandable\b", attrs, re.I) else "<blockquote>"
    return name, f"<{name}>"


def sanitize_tg(text: str | None) -> str:
    """Telegram parse_mode=HTML uchun xavfsiz matn: ruxsat etilgan teglar qoladi, qolgani escape qilinadi."""
    text = text or ""
    if "<" not in text and "&" not in text and ">" not in text:
        return text
    out, stack, pos = [], [], 0
    for m in _TAG.finditer(text):
        out.append(_esc_text(text[pos:m.start()]))
        pos = m.end()
        closing, name, attrs = m.group(1) == "/", m.group(2).lower(), m.group(3) or ""
        canon = "tg-spoiler" if (name == "span" and closing) else name
        if closing:
            if canon == "span" or canon not in stack:
                # span yopilishi: ochilgan tg-spoiler bo'lsa shuni yopamiz
                if name == "span" and "tg-spoiler" in stack:
                    canon = "tg-spoiler"
                else:
                    continue                       # ochilmagan teg yopilishi — tashlab yuboriladi
            while stack:
                top = stack.pop()
                out.append(f"</{top}>")
                if top == canon:
                    break
        else:
            res = _open_tag(name, attrs)
            if res is None:
                out.append(_esc_text(m.group(0)))
            else:
                stack.append(res[0])
                out.append(res[1])
    out.append(_esc_text(text[pos:]))
    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


def to_plain(text: str | None) -> str:
    """Instagram/YouTube va boshqalar uchun: teglar olib tashlanadi, havola «matn (url)» bo'ladi."""
    text = text or ""
    if "<" not in text and "&" not in text:
        return text
    s = sanitize_tg(text)

    def link(m):
        inner = re.sub(r"</?[^>]+>", "", m.group(2))
        url = html.unescape(m.group(1))
        return inner if (not inner.strip() or inner.strip() == url) else f"{inner} ({url})"

    s = re.sub(r'<a href="([^"]*)">(.*?)</a>', link, s, flags=re.S)
    s = re.sub(r"</?[^>]+>", "", s)
    return html.unescape(s)


def visible_len(text: str | None) -> int:
    """Telegram chegarasi (4096 / 1024) teglarsiz, entity'lar ochilgan matn bo'yicha hisoblanadi."""
    s = sanitize_tg(text)
    return len(html.unescape(re.sub(r"</?[^>]+>", "", s)))


def for_platform(text: str | None, platform: str) -> str:
    return sanitize_tg(text) if platform == "telegram" else to_plain(text)


def plain_len(text: str | None, platform: str) -> int:
    return visible_len(text) if platform == "telegram" else len(to_plain(text))
