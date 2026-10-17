"""AI mentor (bilimlar bazasi asosida) va botni AI bilan avtomatik tayyorlash. Umumiy SMM `ai_router` (OpenAI/Claude) ishlatiladi."""
from __future__ import annotations

import re
from datetime import timedelta

from django.utils import timezone

from . import defaults as D
from .models import AiLog, KnowledgeDoc, Lead

_WORD = re.compile(r"[\w'ʻ’`]{3,}", re.U)


class AiLimit(Exception):
    def __init__(self, limit):
        super().__init__(f"limit {limit}")
        self.limit = limit


def daily_limit(project, lead: Lead | None) -> int:
    from .services import active_sub, is_staff
    if lead is None:
        return 0
    if lead.exempt or is_staff(project, lead.tg_id):
        return 0
    return project.ai_sub_daily if active_sub(lead) else project.ai_free_daily


def used_today(project, lead: Lead) -> int:
    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return AiLog.objects.filter(project=project, lead=lead, test=False, at__gte=start).count()


def _chunks(text: str, size: int = 700) -> list[str]:
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text or ""):
        para = para.strip()
        if not para:
            continue
        if len(cur) + len(para) > size and cur:
            out.append(cur)
            cur = ""
        cur += ("\n" if cur else "") + para
        while len(cur) > size * 2:
            out.append(cur[:size * 2])
            cur = cur[size * 2:]
    if cur:
        out.append(cur)
    return out


def retrieve(project, question: str, limit_chars: int = 3500) -> str:
    """Oddiy kalit so'z bo'yicha eng mos bo'laklarni tanlaydi (tashqi xizmatsiz)."""
    qw = {w.lower() for w in _WORD.findall(question or "")}
    scored = []
    for d in KnowledgeDoc.objects.filter(project=project, is_active=True):
        for ch in _chunks(d.content):
            cw = {w.lower() for w in _WORD.findall(ch)}
            score = len(qw & cw) + (1 if d.title.lower() in (question or "").lower() else 0)
            scored.append((score, d.title, ch))
    scored.sort(key=lambda x: -x[0])
    out, total = [], 0
    for score, title, ch in scored:
        if total >= limit_chars or (score == 0 and out):
            break
        out.append(f"[{title}]\n{ch}")
        total += len(ch)
    return "\n\n".join(out)


SYSTEM = ("Sen «{name}» loyihasining AI mentorisan. Foydalanuvchiga FAQAT o'zbek tilida (lotin alifbosida), qisqa, aniq va do'stona javob ber. "
          "Javobni asosan quyidagi BILIMLAR BAZASIga tayanib yoz. Bazada javob bo'lmasa, o'ylab topma: «Bu haqida aniq ma'lumotim yo'q, mas'ul shaxsga murojaat qiling» de. "
          "Narx, muddat va telefonni faqat bazadan ol. Javob 1200 belgidan oshmasin.")


def mentor_answer(project, lead: Lead | None, question: str, user=None, test: bool = False, router=None) -> str:
    from apps.ai_router.router import generate
    from apps.ai_router.types import TaskType
    if not test and lead is not None:
        lim = daily_limit(project, lead)
        if lim and used_today(project, lead) >= lim:
            raise AiLimit(lim)
    kb = retrieve(project, question)
    system = SYSTEM.format(name=project.name) + ("\n\nQO'SHIMCHA KO'RSATMA:\n" + project.ai_instructions if project.ai_instructions.strip() else "")
    prompt = f"BILIMLAR BAZASI:\n{kb or '(hozircha bo‘sh)'}\n\nFOYDALANUVCHI SAVOLI:\n{question[:1500]}"
    res, _ = generate(TaskType.LONG_UZ, prompt, kind="online_mentor", user=user, system_extra=system, require_lang=None, router=router)
    ans = (res.text or "").strip()
    AiLog.objects.create(project=project, lead=lead, question=question[:2000], answer=ans[:4000], test=test)
    return ans


BOT_PROMPT = """«{name}» nomli Telegram bot uchun kontent tayyorla. Loyiha haqida ma'lumot:
{brief}

Tariflar: {tariffs}

Faqat JSON qaytar (boshqa matn yo'q), kalitlari:
- "about": botning qisqa tavsifi, 110 belgigacha
- "description": /start dan oldin ko'rinadigan tavsif, 450 belgigacha
- "start_text": salom matni (HTML: <b>, <i> mumkin; {{name}} ismni bildiradi), 500 belgigacha
- "phone_text": telefon raqamini so'rash matni
- "menu_text": bosh menyu matni
- "ai_instructions": AI mentor uchun ko'rsatma (ohang, qoidalar), 600 belgigacha
- "faq": 5-8 ta {{"title": "...", "content": "..."}} — foydalanuvchilar tez-tez so'raydigan savollar va javoblar (faqat brifdagi ma'lumotga tayanib; narx yoki sanani o'ylab topma)
Barcha matn FAQAT o'zbek tilida (lotin), do'stona, aniq. Karta raqami yoki narxni o'ylab topma."""


def generate_bot(project, brief: str, user=None, router=None) -> dict:
    """Brifdan bot matnlarini tayyorlaydi va QORALAMAga yozadi (joriy bot o'zgarmaydi). Tayyorlanganlarni qaytaradi."""
    from apps.ai_router.router import generate
    from apps.ai_router.types import TaskType
    tariffs = "; ".join(f"{t.name} — {D.money(t.price)} so'm / {t.days} kun" for t in project.tariffs.filter(is_active=True)) or "kiritilmagan"
    res, _ = generate(TaskType.LONG_UZ, BOT_PROMPT.format(name=project.name, brief=brief[:3000], tariffs=tariffs), kind="online_botgen", user=user,
                      schema={"json": True}, require_lang=None, router=router)
    data = res.data or {}
    flow = D.get_flow(project, draft=True)
    done = []
    if str(data.get("about", "")).strip():
        project.about = str(data["about"]).strip()[:120]; done.append("about")
    if str(data.get("description", "")).strip():
        project.description = str(data["description"]).strip()[:500]; done.append("description")
    for key, scr in (("start_text", "start"), ("phone_text", "phone"), ("menu_text", "menu")):
        if str(data.get(key, "")).strip():
            flow["screens"][scr]["text"] = str(data[key]).strip()[:3500]; done.append(scr)
    if str(data.get("ai_instructions", "")).strip():
        project.ai_instructions = str(data["ai_instructions"]).strip()[:2000]; done.append("ai_instructions")
    n = 0
    for f in (data.get("faq") or [])[:10]:
        if isinstance(f, dict) and str(f.get("title", "")).strip() and str(f.get("content", "")).strip():
            KnowledgeDoc.objects.create(project=project, title=str(f["title"])[:160], content=str(f["content"])[:4000])
            n += 1
    if n:
        done.append(f"faq×{n}")
    project.brief = brief[:3000]
    project.flow_draft = flow
    project.save()
    return {"done": done, "raw": bool(data)}
