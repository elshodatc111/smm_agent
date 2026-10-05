"""O'zbekcha (lotin) matn evristik tekshiruvi + maxfiy ma'lumotni tozalash."""
from __future__ import annotations

import re

from apps.core.logging_utils import scrub

from .types import LangCheck

UZ_WORDS = set("va bu uchun bilan bo'lib bo'ladi bor yo'q emas ham yoki lekin juda katta kichik yangi eng yaxshi "
               "bizning sizning siz biz men har bir kun oy yil kurs xizmat narx aksiya chegirma qiling qilish "
               "bo'yicha haqida uchun endi hozir bugun ertaga kerak mumkin mijoz mijozlar bizga sizga "
               "salom rahmat qani nima qanday qachon qayerda".split())
RU_WORDS = set("и в не на что это как для или но все так его она они был при от по".split())
EN_WORDS = set("the and for with that this you your are was from have not but all can our".split())
CYR = re.compile(r"[а-яёўқғҳ]", re.I)
LAT = re.compile(r"[a-zA-Z]")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s\-()]{9,}\d)(?!\d)")


def check_uz(text: str) -> LangCheck:
    if not text or len(text.strip()) < 20:
        return LangCheck(True, 1.0, "qisqa matn")
    words = re.findall(r"[\w'ʻʼ`]+", text.lower())
    if not words:
        return LangCheck(False, 0.0, "so'z yo'q")
    norm = [w.replace("ʻ", "'").replace("ʼ", "'").replace("`", "'") for w in words]
    n = len(norm)
    uz = sum(w in UZ_WORDS for w in norm) / n
    ru = sum(w in RU_WORDS for w in norm) / n
    en = sum(w in EN_WORDS for w in norm) / n
    cyr = len(CYR.findall(text)) / max(1, len(CYR.findall(text)) + len(LAT.findall(text)))
    # o'zbekcha lotin belgilari: o', g', sh, ch, ng
    marks = len(re.findall(r"o'|g'|sh|ch|ng", " ".join(norm))) / n
    score = min(1.0, uz * 4 + marks * 0.5) - en * 2 - ru * 2 - (0.5 if cyr > 0.3 else 0)
    if cyr > 0.3:
        return LangCheck(False, max(0, score), "kirill alifbosi (lotin kerak)")
    if en > 0.12 and uz < 0.05:
        return LangCheck(False, max(0, score), "ingliz tilida")
    if ru > 0.12 and uz < 0.05:
        return LangCheck(False, max(0, score), "rus tilida")
    return LangCheck(score >= 0.12, max(0.0, score), "" if score >= 0.12 else "o'zbekcha ishonchsiz")


def scrub_prompt(text: str) -> tuple[str, bool]:
    """Token, kalit, parol, telefon kabi sirlarni niqoblaydi. (yangi_matn, o'zgardimi)"""
    out = scrub(text)
    out = _PHONE.sub("[telefon]", out) if False else out  # telefon biznes faktlarida kerak bo'lishi mumkin; niqoblanmaydi
    return out, out != text
