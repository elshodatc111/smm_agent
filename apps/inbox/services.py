"""Murojaatlar mantig'i (Telegram'dan mustaqil, to'liq testlanadi): kiruvchi/chiquvchi xabarlar, 15 daqiqalik kutish,
skript asosidagi AI javobi, operatorga uzatish, jurnal, skriptning o'sishi (ScriptGap -> ScriptEntry)."""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.notify import notify

from .models import AIReplyLog, Conversation, InboxAccount, Message, ScriptEntry, ScriptGap

log = logging.getLogger(__name__)

DISCLOSURE = "Assalomu alaykum! Men AI yordamchiman (operator emasman): operator hozir band, shuning uchun savolingizga men javob beraman. "
HANDOFF_TEXT = "Savolingiz operatorga uzatildi, u tez orada o'zi javob beradi. Iltimos, biroz kuting."
BUILTIN_HANDOFF = ("shikoyat", "pulni qaytar", "pul qaytar", "aldadi", "aldov", "sudga", "prokuratura", "advokat", "operator", "odam bilan",
                   "jonli odam", "menejer bilan", "оператор", "жалоб", "верните деньги", "обман")
MAX_AI_STREAK = 6          # operator yozmaguncha ketma-ket AI javoblari chegarasi


# ------------------------------------------------------------------ yordamchilar
_GREET = re.compile(r"^\s*(assalomu\s+alaykum|salom|hayrli\s+(kun|tong|kech))[\s!,.:;—-]*", re.I)


def strip_greeting(text: str) -> str:
    """Tanishtiruvda salomlashuv bor: AI javobining boshidagi takroriy «Assalomu alaykum!» olib tashlanadi."""
    out = _GREET.sub("", text or "", count=1).lstrip()
    return (out[:1].upper() + out[1:]) if out else text


def disclosure(acc) -> str:
    """Birinchi AI javobidagi tanishtiruv: «Men AI Alisaman (operator emasman)…» (ism akkauntda kiritiladi)."""
    n = (getattr(acc, "ai_name", "") or "").strip()
    if not n:
        return DISCLOSURE
    return f"Assalomu alaykum! Men AI {n}man (operator emasman): operator hozir band, shuning uchun savolingizga men javob beraman. "


def normalize_key(text: str) -> str:
    t = re.sub(r"[^\w\s]", " ", (text or "").lower())
    words = [w for w in t.split() if len(w) > 2][:8]
    return " ".join(words)[:80]


def _words(text: str) -> set[str]:
    return {w for w in re.sub(r"[^\w\s]", " ", (text or "").lower()).split() if len(w) > 2}


def _nums(text: str) -> set[str]:
    return set(re.findall(r"\d[\d\s.,]*\d|\d", (text or "")))


def _norm_num(n: str) -> str:
    return re.sub(r"[\s.,]", "", n)


# ------------------------------------------------------------------ kiruvchi / chiquvchi
@transaction.atomic
def ingest_inbound(account: InboxAccount, peer_id: int, text: str, *, name: str = "", username: str = "", tg_msg_id: int | None = None, when=None) -> Message:
    when = when or timezone.now()
    if tg_msg_id and Message.objects.filter(conversation__account=account, conversation__peer_id=peer_id, tg_msg_id=tg_msg_id, direction="in").exists():
        return Message.objects.get(conversation__account=account, conversation__peer_id=peer_id, tg_msg_id=tg_msg_id, direction="in")
    conv, created = Conversation.objects.get_or_create(account=account, peer_id=peer_id, defaults={"business": account.business, "peer_name": name[:160], "peer_username": username[:80]})
    if not created:
        changed = []
        if name and conv.peer_name != name[:160]:
            conv.peer_name = name[:160]; changed.append("peer_name")
        if username and conv.peer_username != username[:80]:
            conv.peer_username = username[:80]; changed.append("peer_username")
        if changed:
            conv.save(update_fields=changed)
    msg = Message.objects.create(conversation=conv, direction="in", sender="customer", text=(text or "")[:4000], tg_msg_id=tg_msg_id, state="received", created_at=when)
    conv.status, conv.unread, conv.last_message_at, conv.last_inbound_at = "open", True, when, when
    conv.save(update_fields=["status", "unread", "last_message_at", "last_inbound_at"])
    notify("inbox.new", f"Yangi murojaat: {conv}", (text or "")[:140], business_id=conv.business_id, link=f"/murojaatlar/{conv.pk}/",
           dedupe_key=f"inbox-new:{conv.pk}", dedupe_minutes=int(account.wait_minutes or 15))
    return msg


@transaction.atomic
def ingest_outgoing_human(account: InboxAccount, peer_id: int, text: str, *, tg_msg_id: int | None = None, when=None) -> Message | None:
    """Operator Telegram ilovasining o'zidan yozgan xabar (tizim yuborganlari tg_msg_id bo'yicha takrorlanmaydi)."""
    when = when or timezone.now()
    conv = Conversation.objects.filter(account=account, peer_id=peer_id).first()
    if conv is None:
        return None      # mijoz birinchi yozmagan suhbat — kuzatmaymiz
    if tg_msg_id and Message.objects.filter(conversation=conv, tg_msg_id=tg_msg_id, direction="out").exists():
        return None
    # tizim o'zi yuborgan xabar hodisasi (tg_msg_id hali saqlanmagan bo'lishi mumkin) — operator javobi hisoblanmaydi
    if Message.objects.filter(conversation=conv, direction="out", text=(text or "")[:4000], created_at__gte=when - timedelta(minutes=3)).exclude(sender="customer").exists():
        return None
    msg = Message.objects.create(conversation=conv, direction="out", sender="operator", text=(text or "")[:4000], tg_msg_id=tg_msg_id, state="sent", created_at=when)
    _operator_replied(conv, when)
    return msg


def _operator_replied(conv: Conversation, when) -> None:
    conv.needs_human, conv.human_reason, conv.unread, conv.last_message_at = False, "", False, when
    conv.save(update_fields=["needs_human", "human_reason", "unread", "last_message_at"])


def queue_outbound(conv: Conversation, text: str, *, sender: str, user=None, when=None) -> Message:
    """Chiquvchi xabarni navbatga qo'yadi; haqiqiy yuborishni listener bajaradi (flush_pending)."""
    when = when or timezone.now()
    msg = Message.objects.create(conversation=conv, direction="out", sender=sender, text=text[:4000], state="pending", by_user=user, created_at=when)
    if sender == "operator":
        _operator_replied(conv, when)
    else:
        conv.last_message_at = when
        conv.save(update_fields=["last_message_at"])
    return msg


def pending_for(account: InboxAccount, limit: int = 5) -> list[tuple[int, int, str]]:
    """[(message_pk, peer_id, text)] — shu akkaunt orqali yuborilishi kerak bo'lganlar."""
    qs = Message.objects.filter(conversation__account=account, direction="out", state="pending").select_related("conversation").order_by("created_at")[:limit]
    return [(m.pk, m.conversation.peer_id, m.text) for m in qs]


def mark_sent(pk: int, tg_msg_id: int | None) -> None:
    Message.objects.filter(pk=pk).update(state="sent", tg_msg_id=tg_msg_id, error="")


def mark_failed(pk: int, err: str) -> None:
    Message.objects.filter(pk=pk).update(state="failed", error=str(err)[:290])


def flush_pending(account: InboxAccount, send_fn, *, limit: int = 5) -> int:
    """Sinxron variant (testlar uchun): send_fn(peer_id, text) -> tg_msg_id."""
    n = 0
    for pk, peer_id, text in pending_for(account, limit):
        try:
            mark_sent(pk, send_fn(peer_id, text))
            n += 1
        except Exception as e:  # noqa: BLE001
            mark_failed(pk, str(e))
            log.warning("inbox yuborish xatosi: %s", e)
    return n


# ------------------------------------------------------------------ kutish va javob berishga tayyorlik
def awaiting_message(conv: Conversation) -> Message | None:
    """Javobsiz qolgan eng eski kiruvchi xabar (oxirgi chiquvchi xabardan keyingi)."""
    last_out = conv.messages.filter(direction="out").exclude(state="failed").order_by("-created_at", "-pk").first()
    qs = conv.messages.filter(direction="in")
    if last_out:
        qs = qs.filter(created_at__gt=last_out.created_at)
    return qs.order_by("created_at", "pk").first()


def ai_mode(conv: Conversation, now=None) -> bool:
    """AI rejimi: oxirgi javob AI'niki, operator aralashmagan va undan beri AI sessiyasi vaqti o'tmagan."""
    now = now or timezone.now()
    last_out = conv.messages.filter(direction="out").exclude(state="failed").order_by("-created_at", "-pk").first()
    if not last_out or last_out.sender != "ai":
        return False
    return now - last_out.created_at <= timedelta(minutes=int(conv.account.ai_session_minutes or 180))


def ai_join_at(conv: Conversation, now=None):
    """AI qachon javob bera oladi.
    Operator rejimi: eng eski javobsiz xabardan + wait_minutes (operatorga vaqt beriladi).
    AI rejimi: mijozning OXIRGI xabaridan + ai_delay_seconds (ketma-ket xabarlar bitta javobga yig'iladi)."""
    m = awaiting_message(conv)
    if not m:
        return None
    if ai_mode(conv, now):
        last_in = conv.messages.filter(direction="in", created_at__gte=m.created_at).order_by("-created_at", "-pk").first() or m
        return last_in.created_at + timedelta(seconds=int(conv.account.ai_delay_seconds or 30))
    return m.created_at + timedelta(minutes=int(conv.account.wait_minutes or 15))


def due_conversations(account: InboxAccount, now=None):
    now = now or timezone.now()
    if not account.active or not account.auto_reply:
        return []
    if account.cooldown_until and account.cooldown_until > now:
        return []
    out = []
    for conv in account.conversations.filter(status="open", ai_enabled=True, needs_human=False, last_inbound_at__isnull=False):
        at = ai_join_at(conv, now)
        if at and at <= now:
            out.append(conv)
    return out


def _ai_count_last_hour(account: InboxAccount, now) -> int:
    return Message.objects.filter(conversation__account=account, sender="ai", created_at__gte=now - timedelta(hours=1)).count()


def _ai_streak(conv: Conversation) -> int:
    n = 0
    for m in conv.messages.filter(direction="out").order_by("-created_at", "-pk")[:MAX_AI_STREAK + 2]:
        if m.sender != "ai":
            break
        n += 1
    return n


# ------------------------------------------------------------------ skript
def script_for(business) -> list[ScriptEntry]:
    return list(ScriptEntry.objects.filter(business=business, active=True))


def _rank(entries: list[ScriptEntry], text: str, limit: int = 12) -> list[ScriptEntry]:
    qa = [e for e in entries if e.kind == "qa"]
    w = _words(text)
    scored = sorted(qa, key=lambda e: -len(w & _words(f"{e.title} {e.questions} {e.answer}")))
    return scored[:limit]


def _handoff_words(entries: list[ScriptEntry]) -> list[str]:
    extra = []
    for e in entries:
        if e.kind == "handoff":
            extra += [x.strip().lower() for x in (e.questions or "").splitlines() if x.strip()]
    return list(BUILTIN_HANDOFF) + extra


def _history(conv: Conversation, n: int = 10) -> str:
    rows = list(conv.messages.exclude(state="failed").order_by("-created_at", "-pk")[:n])[::-1]
    who = {"customer": "Mijoz", "operator": "Operator", "ai": "AI"}
    return "\n".join(f"{who.get(m.sender, m.sender)}: {m.text[:400]}" for m in rows)


def _prompt(conv: Conversation, entries: list[ScriptEntry], question: str) -> str:
    rules = [e for e in entries if e.kind == "rule"]
    qa = _rank(entries, question + " " + _history(conv, 4))
    parts = ["Sen biznesning mijozlar bilan yozishuvchi AI yordamchisisan. Quyidagi SKRIPTDAN tashqariga CHIQMA.",
             "QOIDALAR: 1) Faqat skriptdagi ma'lumot bilan javob ber; narx, sana, telefon, manzil yoki va'dani skriptda yo'q bo'lsa O'YLAB TOPMA. "
             "2) Skriptdan javob topa olmasang yoki mijoz shikoyat/pul qaytarish/operator so'rasa — handoff=true qil. "
             "3) Mijoz qaysi tilda (o'zbek yoki rus) yozsa, shu tilda yoz. Qisqa, iliq, 600 belgidan oshmasin. 4) O'zingni inson deb tanishtirma."
             + (f" Sening isming: AI {conv.account.ai_name}. Ismingni so'rashsa shuni ayt; javob matniga salomlashish va o'zingni tanishtirishni qo'shma (u avtomatik qo'shiladi)." if conv.account.ai_name else ""),
             "Javob FAQAT JSON: {\"answer\": \"...\", \"handoff\": false, \"reason\": \"\", \"used\": [skript_id,...], \"missing_question\": \"\"}"]
    if rules:
        parts.append("UMUMIY QOIDALAR:\n" + "\n".join(f"- {r.title}: {r.answer}" for r in rules))
    if qa:
        parts.append("SKRIPT:\n" + "\n".join(f"[id={e.pk}] {e.title}\n  Savollar: {' | '.join(x.strip() for x in e.questions.splitlines() if x.strip())[:300]}\n  Javob: {e.answer}" for e in qa))
    else:
        parts.append("SKRIPT: (bo'sh)")
    parts.append(f"SUHBAT:\n{_history(conv)}\n\nMijozning oxirgi xabari: {question}")
    return "\n\n".join(parts)


def record_gap(business, question: str, conv: Conversation | None = None) -> ScriptGap | None:
    key = normalize_key(question)
    if not key:
        return None
    gap = ScriptGap.objects.filter(business=business, key=key, status="new").first()
    if gap:
        gap.count += 1
        gap.conversation = conv or gap.conversation
        gap.save(update_fields=["count", "conversation", "last_seen_at"])
        return gap
    return ScriptGap.objects.create(business=business, question=question[:600], key=key, conversation=conv)


def _log(conv, decision, question="", answer="", reason="", script_ids=None, res=None) -> AIReplyLog:
    return AIReplyLog.objects.create(business=conv.business, conversation=conv, decision=decision, question=question[:1500], answer=answer[:2000], reason=reason[:300],
                                     script_ids=script_ids or [], provider=getattr(res, "provider", "") or "", model=getattr(res, "model", "") or "",
                                     tokens_in=getattr(res, "tokens_in", 0) or 0, tokens_out=getattr(res, "tokens_out", 0) or 0)


def _handoff(conv: Conversation, question: str, reason: str, res=None, missing: str = "") -> dict:
    conv.needs_human, conv.human_reason = True, reason[:200]
    fields = ["needs_human", "human_reason"]
    if not conv.handoff_notified:
        txt = HANDOFF_TEXT if conv.ai_disclosed else disclosure(conv.account) + HANDOFF_TEXT
        queue_outbound(conv, txt, sender="ai")
        conv.handoff_notified = conv.ai_disclosed = True
        fields += ["handoff_notified", "ai_disclosed"]
    conv.save(update_fields=fields)
    if reason != "mijoz operator so'radi":
        record_gap(conv.business, missing or question, conv)
    notify("inbox.handoff", f"Operator kerak: {conv}", f"{reason}: {question[:120]}", business_id=conv.business_id, severity="warn",
           link=f"/murojaatlar/{conv.pk}/", dedupe_key=f"inbox-handoff:{conv.pk}", dedupe_minutes=60)
    _log(conv, "handoff", question, "", reason, res=res)
    return {"decision": "handoff", "reason": reason}


def _grounded(answer: str, entries: list[ScriptEntry], conv: Conversation) -> bool:
    """Javobdagi raqamlar (narx, telefon, sana) skriptda yoki mijoz yozganlarida bo'lishi shart."""
    allowed = {_norm_num(n) for n in _nums(" ".join(f"{e.title} {e.questions} {e.answer}" for e in entries))}
    allowed |= {_norm_num(n) for n in _nums(" ".join(m.text for m in conv.messages.filter(direction="in")[:30]))}
    return all(_norm_num(n) in allowed for n in _nums(answer) if len(_norm_num(n)) >= 2)


def auto_reply(conv: Conversation, *, now=None, router=None) -> dict:
    """Bitta suhbat uchun AI qarori. Qaytaradi: {'decision': answered|handoff|skipped|failed, ...}."""
    now = now or timezone.now()
    acc = conv.account
    if not (acc.active and acc.auto_reply and conv.ai_enabled and conv.status == "open") or conv.needs_human:
        return {"decision": "skipped", "reason": "o'chiq yoki operator kerak"}
    wait = awaiting_message(conv)
    if wait is None:
        return {"decision": "skipped", "reason": "javobsiz xabar yo'q"}
    at = ai_join_at(conv, now)
    if at is None or now < at:
        return {"decision": "skipped", "reason": "operator kutilmoqda"}
    if _ai_count_last_hour(acc, now) >= int(acc.hourly_limit or 30):
        return {"decision": "skipped", "reason": "soatlik limit"}
    if _ai_streak(conv) >= MAX_AI_STREAK:
        return _handoff(conv, wait.text, "AI ketma-ket javoblari chegarasi")
    entries = script_for(conv.business)
    question = "\n".join(m.text for m in conv.messages.filter(direction="in", created_at__gte=wait.created_at).order_by("created_at")[:6])[:1500]
    low = question.lower()
    if any(w in low for w in _handoff_words(entries)):
        return _handoff(conv, question, "mijoz operator so'radi" if "operator" in low or "оператор" in low or "odam" in low else "ehtiyotkor mavzu (shikoyat/pul)")
    if not any(e.kind == "qa" for e in entries):
        return _handoff(conv, question, "skript bo'sh")
    from apps.ai_router.router import AIUnavailable, generate
    from apps.ai_router.types import TaskType
    try:
        res, _gen = generate(TaskType.COMMENT_REPLY, _prompt(conv, entries, question), business=conv.business, kind="inbox_reply", schema={"json": True}, router=router, require_lang=None)
    except AIUnavailable as e:
        _log(conv, "failed", question, "", str(e)[:200])
        return {"decision": "failed", "reason": str(e)[:200]}
    d = res.data if isinstance(res.data, dict) else {}
    answer = str(d.get("answer") or "").strip()
    used = [i for i in (d.get("used") or []) if isinstance(i, int)]
    if d.get("handoff") or not answer:
        return _handoff(conv, question, str(d.get("reason") or "skriptda javob yo'q")[:150], res, str(d.get("missing_question") or ""))
    if not _grounded(answer, entries, conv):
        return _handoff(conv, question, "javobdagi raqam skriptda yo'q (o'ylab topilgan bo'lishi mumkin)", res, question)
    answer = answer[:900]
    text = answer if conv.ai_disclosed else disclosure(acc) + strip_greeting(answer)
    queue_outbound(conv, text, sender="ai", when=now)
    if not conv.ai_disclosed:
        conv.ai_disclosed = True
        conv.save(update_fields=["ai_disclosed"])
    valid = [i for i in used if any(e.pk == i for e in entries)]
    ScriptEntry.objects.filter(pk__in=valid).update(uses=F("uses") + 1)
    _log(conv, "answered", question, text, "", valid, res)
    return {"decision": "answered", "text": text}


def process_account(account: InboxAccount, *, now=None, router=None) -> list[dict]:
    now = now or timezone.now()
    out = []
    for conv in due_conversations(account, now):
        try:
            out.append({"conv": conv.pk, **auto_reply(conv, now=now, router=router)})
        except Exception:  # noqa: BLE001
            log.exception("inbox auto_reply xatosi (conv %s)", conv.pk)
    return out


# ------------------------------------------------------------------ operatorga yordam
def suggest_replies(conv: Conversation, user=None, router=None) -> list[dict]:
    """Operator uchun 3 ta javob varianti (skript va yozishma asosida). Hech narsa avtomatik yuborilmaydi."""
    from apps.ai_router.router import generate
    from apps.ai_router.types import TaskType
    entries = script_for(conv.business)
    last = conv.messages.filter(direction="in").order_by("-created_at").first()
    prompt = (_prompt(conv, entries, last.text if last else "") .split("Javob FAQAT JSON")[0]
              + "Operator uchun 3 xil javob varianti yoz: 1) qisqa, 2) batafsil, 3) sotuvga yo'naltiruvchi. Skriptda yo'q narx/sanani o'ylab topma, kerak joyga [to'ldiring] qo'y.\n"
              'Javob FAQAT JSON: {"options": [{"label": "Qisqa", "text": ""}, {"label": "Batafsil", "text": ""}, {"label": "Sotuvga yo\'naltiruvchi", "text": ""}]}\n\n'
              f"SUHBAT:\n{_history(conv)}")
    res, _ = generate(TaskType.COMMENT_REPLY, prompt, business=conv.business, kind="inbox_suggest", user=user, schema={"json": True}, router=router, require_lang=None)
    opts = (res.data or {}).get("options") if isinstance(res.data, dict) else None
    return [{"label": str(o.get("label", ""))[:40], "text": str(o.get("text", ""))[:900]} for o in (opts or []) if isinstance(o, dict) and o.get("text")][:3]


def add_to_script(conv: Conversation, operator_msg: Message, user=None) -> ScriptEntry | None:
    """Operator javobini skriptga qo'shadi: oldingi mijoz savoli + operator javobi (skript yozishmalardan o'sadi)."""
    if operator_msg.direction != "out" or operator_msg.sender != "operator" or operator_msg.conversation_id != conv.pk:
        return None
    q = conv.messages.filter(direction="in", created_at__lte=operator_msg.created_at).order_by("-created_at").first()
    if not q:
        return None
    entry = ScriptEntry.objects.create(business=conv.business, kind="qa", title=q.text[:80], questions=q.text[:500], answer=operator_msg.text[:1500], source="learned", created_by=user)
    ScriptGap.objects.filter(business=conv.business, key=normalize_key(q.text), status="new").update(status="added")
    return entry


def stats(business_ids) -> dict:
    now = timezone.now()
    convs = Conversation.objects.filter(business_id__in=business_ids, status="open")
    waiting = [c for c in convs.filter(needs_human=False) if awaiting_message(c)]
    return {"open": convs.count(), "waiting": len(waiting), "needs_human": convs.filter(needs_human=True).count(),
            "ai_today": AIReplyLog.objects.filter(business_id__in=business_ids, decision="answered", created_at__gte=now - timedelta(days=1)).count()}
