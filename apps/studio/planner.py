"""Kontent reja: har ijtimoiy tarmoq uchun ALOHIDA oylik reja.

Ish tartibi:
1. `build_slots` — kod (AIsiz) oyni bo'laklarga ajratadi: sana, vaqt, format, kontent ustuni (pillar) va andozadan boshlang'ich mavzu.
   Ustunlar ulushi, sotuv postlari chegarasi, format xilma-xilligi va bayram/mavsum shu yerda kafolatlanadi.
2. `create_plan` — shu bo'laklardan darhol ishlaydigan reja yaratadi (AI ishlamasa ham reja tayyor turadi).
3. `fill_with_ai` — AI har bo'lak uchun mavzu/hook/CTA/vazifani biznes pasportiga moslab yozadi. Xato bo'lsa andoza matni qoladi.
Kontent tili FAQAT o'zbekcha (lotin): kirill yoki begona tilda javob kelsa, o'sha qator andoza matni bilan almashtiriladi.
"""
from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import date, datetime, time, timedelta

from apps.ai_router.router import generate
from apps.ai_router.types import TaskType
from apps.businesses.playbooks import playbook_for
from apps.core.utils import tz

from .models import ContentPlan

J = {"json": True}

PLATFORMS = [("telegram", "Telegram"), ("instagram", "Instagram"), ("youtube", "YouTube")]
PLATFORM_UZ = dict(PLATFORMS)

# Platformada mumkin bo'lgan formatlar (ContentItem.media_type qiymatlari bilan bir xil)
FORMAT_UZ = {"text": "Matnli post", "image": "Rasmli post", "video": "Video", "carousel": "Karusel", "reel": "Reels",
             "short": "Shorts", "story": "Stories"}
PLATFORM_FORMATS = {
    "telegram": ["text", "image", "carousel", "video"],
    "instagram": ["image", "carousel", "reel", "story"],
    "youtube": ["short", "video"],
}
# andozadagi umumiy format -> platforma formati
FMT_MAP = {
    "post": {"telegram": "image", "instagram": "image", "youtube": "short"},
    "carousel": {"telegram": "carousel", "instagram": "carousel", "youtube": "video"},
    "reel": {"telegram": "video", "instagram": "reel", "youtube": "short"},
    "video": {"telegram": "video", "instagram": "reel", "youtube": "video"},
    "story": {"telegram": "text", "instagram": "story", "youtube": "short"},
}
# haftasiga standart postlar soni va nashr vaqti
DEFAULT_PPW = {"telegram": 5, "instagram": 4, "youtube": 2}
PUBLISH_TIME = {"telegram": time(12, 0), "instagram": time(19, 0), "youtube": time(18, 0)}
WEEKDAY_SETS = {1: [2], 2: [1, 4], 3: [0, 2, 4], 4: [0, 2, 3, 5], 5: [0, 1, 3, 4, 5], 6: [0, 1, 2, 3, 4, 5], 7: [0, 1, 2, 3, 4, 5, 6]}
WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
MONTHS_UZ = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]

# O'zbekistondagi sanalar (qat'iy sanali bayramlar); harakatlanuvchi sanalar (hayitlar) foydalanuvchi qo'lida qoladi
HOLIDAYS = {
    (1, 1): "Yangi yil", (1, 14): "Vatan himoyachilari kuni", (3, 8): "Xalqaro xotin-qizlar kuni", (3, 21): "Navro'z bayrami",
    (5, 9): "Xotira va qadrlash kuni", (6, 1): "Bolalar himoyasi kuni", (9, 1): "Mustaqillik kuni", (10, 1): "O'qituvchi va murabbiylar kuni",
    (12, 8): "Konstitutsiya kuni",
}

_CYR = re.compile(r"[Ѐ-ӿ]")
_WORD = re.compile(r"[a-zA-ZЀ-ӿ'`ʻʼ]{3,}")


def is_uzbek_latin(text: str) -> bool:
    """Kirill (rus/o'zbek kirill) bo'lsa — False. Kontent tili faqat o'zbek lotin."""
    return not _CYR.search(text or "")


def _norm(s: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(s or "")}


def similar(a: str, b: str) -> bool:
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return False
    return len(x & y) / len(x | y) >= 0.7


def parse_ppw(capacity: str, platform: str) -> int:
    """Pasportdagi «Kontent uchun imkoniyat» matnidan haftalik post sonini topadi (yo'q bo'lsa — standart)."""
    d = DEFAULT_PPW.get(platform, 3)
    m = re.search(r"(\d{1,2})\s*(?:ta|marta|dona|post|video)?", capacity or "")
    if m:
        n = int(m.group(1))
        if 1 <= n <= 14:
            return max(1, min(d, n))
    return d


def _capacity(business) -> str:
    return ((business.profile or {}).get("general") or {}).get("capacity", "") or ""


def _season(business, month: int) -> str:
    pb = playbook_for(business)
    return (pb.get("seasonality") or {}).get(month, "")


def _pick_format(platform: str, idea_fmt: str, recent: list[str]) -> str:
    allowed = PLATFORM_FORMATS[platform]
    f = FMT_MAP.get(idea_fmt, FMT_MAP["post"]).get(platform, allowed[0])
    if f not in allowed:
        f = allowed[0]
    # uch marta ketma-ket bir xil format bo'lmasin
    if len(recent) >= 2 and recent[-1] == recent[-2] == f:
        alt = [x for x in allowed if x != f]
        if alt:
            f = alt[len(recent) % len(alt)]
    return f


def build_slots(business, platform: str, month: date, *, ppw: int | None = None, today: date | None = None) -> list[dict]:
    pb = playbook_for(business)
    pillars = pb["pillars"]
    ppw = ppw or parse_ppw(_capacity(business), platform)
    ppw = max(1, min(7, ppw))
    days = monthrange(month.year, month.month)[1]
    today = today or datetime.now(tz()).date()
    wd = set(WEEKDAY_SETS[ppw])
    dates = [date(month.year, month.month, d) for d in range(1, days + 1)]
    dates = [d for d in dates if d.weekday() in wd and d >= today]

    ideas_by_pillar: dict[str, list[dict]] = {}
    for it in pb["ideas"]:
        ideas_by_pillar.setdefault(it["pillar"], []).append(it)
    used_idx: dict[str, int] = {}
    counts = {p["key"]: 0 for p in pillars}
    total_share = sum(p["share"] for p in pillars) or 100
    ctas = pb.get("cta") or ["Bizga yozing"]
    slots: list[dict] = []
    recent_fmt: list[str] = []
    prev_pillar = ""
    for i, d in enumerate(dates):
        # ulush bo'yicha eng "qarzdor" ustunni tanlaymiz; sotuv ketma-ket kelmasin
        n = i + 1
        best, best_def = None, -1e9
        for p in pillars:
            if p["key"] == "sotuv" and prev_pillar == "sotuv":
                continue
            if p["key"] == prev_pillar and len(pillars) > 1:
                continue
            deficit = p["share"] / total_share * n - counts[p["key"]]
            if deficit > best_def:
                best, best_def = p, deficit
        best = best or pillars[0]
        counts[best["key"]] += 1
        prev_pillar = best["key"]
        pool = ideas_by_pillar.get(best["key"]) or pb["ideas"]
        k = used_idx.get(best["key"], 0)
        idea = pool[k % len(pool)]
        used_idx[best["key"]] = k + 1
        fmt = _pick_format(platform, idea["format"], recent_fmt)
        recent_fmt.append(fmt)
        slots.append({"date": d.isoformat(), "time": PUBLISH_TIME[platform].strftime("%H:%M"), "weekday": WEEKDAYS_UZ[d.weekday()],
                      "platform": platform, "format": fmt, "pillar": best["key"], "pillar_name": best["name"],
                      "topic": idea["topic"], "hook": idea["hook"], "cta": ctas[i % len(ctas)], "goal": best["name"],
                      "brief": "", "occasion": "", "source": "andoza"})
    # bayramlarni eng yaqin (shu kun yoki undan oldingi) bo'lakka biriktiramiz
    for (m, dd), name in HOLIDAYS.items():
        if m != month.month or dd > days:
            continue
        hd = date(month.year, m, dd)
        cand = [s for s in slots if date.fromisoformat(s["date"]) <= hd]
        tgt = cand[-1] if cand and (hd - date.fromisoformat(cand[-1]["date"])).days <= 3 else None
        if tgt is None:
            later = [s for s in slots if date.fromisoformat(s["date"]) > hd]
            tgt = later[0] if later and (date.fromisoformat(later[0]["date"]) - hd).days <= 2 else None
        if tgt and not tgt["occasion"]:
            tgt["occasion"] = f"{hd.day}-{MONTHS_UZ[m]}: {name}"
    return slots


def strategy_for(business, platform: str, ppw: int, month: date, slots: list[dict]) -> dict:
    pb = playbook_for(business)
    cnt: dict[str, int] = {}
    for s in slots:
        cnt[s["pillar"]] = cnt.get(s["pillar"], 0) + 1
    return {
        "platform": platform, "ppw": ppw, "total": len(slots), "season": _season(business, month.month),
        "pillars": [{**p, "count": cnt.get(p["key"], 0)} for p in pb["pillars"]],
        "avoid": pb.get("avoid", []), "goal": "", "tone": "", "key_messages": [],
    }


def create_plan(business, platform: str, month: date, user=None, *, ppw: int | None = None, focus: str = "") -> ContentPlan:
    """Darhol ishlaydigan (andozaga asoslangan) reja yaratadi. AI to'ldirish alohida (`fill_with_ai`)."""
    month = month.replace(day=1)
    ppw = max(1, min(7, ppw or parse_ppw(_capacity(business), platform)))
    slots = build_slots(business, platform, month, ppw=ppw)
    st = strategy_for(business, platform, ppw, month, slots)
    st["focus"] = (focus or "").strip()[:500]
    st["ai_state"] = "pending"
    summary = (f"{PLATFORM_UZ[platform]} uchun {MONTHS_UZ[month.month]} oyi rejasi: haftasiga {ppw} ta nashr, jami {len(slots)} ta. "
               + (f"Mavsum: {st['season']}." if st["season"] else ""))
    return ContentPlan.objects.create(business=business, platform=platform, month=month, entries=slots, summary=summary,
                                      strategy=st, status="draft", created_by=user)


def _recent_topics(business, plan: ContentPlan | None = None, days: int = 60) -> list[str]:
    from apps.content.models import ContentItem
    since = datetime.now(tz()) - timedelta(days=days)
    qs = ContentItem.objects.filter(business=business, created_at__gte=since)
    if plan is not None:
        qs = qs.exclude(plan=plan)
    out = list(qs.values_list("title", flat=True)[:60])
    for p in ContentPlan.objects.filter(business=business, created_at__gte=since).exclude(pk=getattr(plan, "pk", None))[:6]:
        out += [e.get("topic", "") for e in p.entries if e.get("topic")]
    return [t for t in out if t][:80]


def _ai_prompt(plan: ContentPlan, only: list[int] | None = None) -> str:
    from apps.businesses import passport
    b = plan.business
    pb = playbook_for(b)
    st = plan.strategy or {}
    items = [{"i": i, "sana": e["date"], "hafta_kuni": e.get("weekday"), "format": FORMAT_UZ.get(e["format"], e["format"]),
              "ustun": e.get("pillar_name"), "boshlangich_mavzu": e.get("topic"), "bayram": e.get("occasion", "")}
             for i, e in enumerate(plan.entries) if only is None or i in only]
    recent = _recent_topics(b, plan)
    return (
        f"Sen {b.name} biznesi uchun tajribali SMM-strateg va kontent-muharrirsan. {PLATFORM_UZ[plan.platform]} uchun "
        f"{MONTHS_UZ[plan.month.month]} {plan.month.year} oyi kontent-rejasini BIZNESGA MOSLAB to'ldir.\n\n"
        f"BIZNES PASPORTI:\n{passport.brief(b, 2400)}\n\n"
        f"Kontent ustunlari va ulushi: {json.dumps([(p['name'], p['share']) for p in pb['pillars']], ensure_ascii=False)}\n"
        f"Mavsum: {st.get('season') or '—'}. Qo'shimcha e'tibor: {st.get('focus') or '—'}\n"
        f"Taqiqlar: {', '.join(pb.get('avoid', []))}\n"
        f"Oxirgi 60 kunda ishlatilgan mavzular (TAKRORLAMA): {json.dumps(recent[:40], ensure_ascii=False)}\n\n"
        f"BO'LAKLAR (sana, format va ustun TAYYOR, o'zgartirma; faqat mazmunini yoz):\n{json.dumps(items, ensure_ascii=False)}\n\n"
        "Har bo'lak uchun: topic — aniq, shu biznesga xos mavzu (umumiy emas!); hook — birinchi jumla (platforma uchun, 12 so'zgacha); "
        "cta — bitta aniq harakat; goal — maqsad (1-3 so'z); brief — dizayner/operator uchun 1-2 jumla (nima ko'rinadi kadrda). "
        "Sotuv ustunida ham ochiq reklama emas, foyda va ishonch ko'rsat. Bayram bo'lsa — mavzuni unga bog'la.\n"
        'JSON: {"summary":"oy strategiyasi 2-3 jumla","goal":"oy maqsadi","tone":"ohang","key_messages":["3-4 asosiy xabar"],'
        '"entries":[{"i":0,"topic":"","hook":"","cta":"","goal":"","brief":""}]}\n'
        "TIL: faqat o'zbek tili, lotin yozuvida. Kirill, rus va ingliz so'zlarini ishlatma (brend nomlari bundan mustasno). "
        "Aniq narx, telefon, foiz, natija raqamini o'ylab topma; kerak bo'lsa [to'ldiring] deb yoz. Bu TAKLIF: egasi o'zi tahrirlaydi."
    )


def fill_with_ai(plan: ContentPlan, user=None, router=None, only: list[int] | None = None) -> int:
    """AI mazmunni yozadi. Qaytaradi: yangilangan qatorlar soni. Xato bo'lsa — andoza matni saqlanadi va holat 'fallback'."""
    st = dict(plan.strategy or {})
    entries = [dict(e) for e in plan.entries]
    try:
        res, gen = generate(TaskType.LONG_UZ, _ai_prompt(plan, only), business=plan.business, kind="plan", user=user, schema=J, router=router)
        d = res.data or {}
    except Exception as e:  # noqa: BLE001
        st["ai_state"] = "fallback"
        st["ai_error"] = (getattr(e, "user_message_uz", None) or str(e))[:200]
        plan.strategy = st
        plan.save(update_fields=["strategy"])
        return 0
    recent = _recent_topics(plan.business, plan)
    seen = list(recent)
    n = 0
    for row in d.get("entries") or []:
        if not isinstance(row, dict):
            continue
        try:
            i = int(row.get("i"))
        except (TypeError, ValueError):
            continue
        if not (0 <= i < len(entries)) or (only is not None and i not in only):
            continue
        topic = str(row.get("topic") or "").strip()
        hook = str(row.get("hook") or "").strip()
        cta = str(row.get("cta") or "").strip()
        blob = " ".join([topic, hook, cta, str(row.get("brief") or ""), str(row.get("goal") or "")])
        if not topic or not is_uzbek_latin(blob):
            continue  # tilga mos emas — andoza matni qoladi
        if any(similar(topic, t) for t in seen):
            continue  # takror mavzu — andoza matni qoladi
        e = entries[i]
        e.update(topic=topic[:200], hook=hook[:200] or e.get("hook", ""), cta=cta[:160] or e.get("cta", ""),
                 goal=str(row.get("goal") or e.get("goal", ""))[:80], brief=str(row.get("brief") or "")[:400], source="ai")
        seen.append(topic)
        n += 1
    for k in ("goal", "tone"):
        v = str(d.get(k) or "").strip()
        if v and is_uzbek_latin(v):
            st[k] = v[:300]
    km = [str(x) for x in (d.get("key_messages") or []) if isinstance(x, str) and is_uzbek_latin(x)]
    if km:
        st["key_messages"] = km[:5]
    summ = str(d.get("summary") or "").strip()
    st["ai_state"] = "ok" if n else "fallback"
    st.pop("ai_error", None)
    plan.entries = entries
    plan.strategy = st
    if summ and is_uzbek_latin(summ) and only is None:
        plan.summary = summ[:1500]
    plan.generation = gen
    plan.save(update_fields=["entries", "strategy", "summary", "generation"])
    return n


def regenerate_entry(plan: ContentPlan, i: int, user=None, router=None) -> bool:
    """Bitta qatorni qayta yozadi (hozirgi mavzu «takror» hisoblanmasligi uchun avval bo'shatiladi)."""
    if not (0 <= i < len(plan.entries)):
        return False
    old = plan.entries[i].get("topic", "")
    pb = playbook_for(plan.business)
    plan.entries[i]["topic"] = ""
    plan.save(update_fields=["entries"])
    n = fill_with_ai(plan, user, router, only=[i])
    if not n:
        # AI ishlamadi: andozadagi keyingi g'oyani beramiz
        pool = [x for x in pb["ideas"] if x["pillar"] == plan.entries[i].get("pillar") and not similar(x["topic"], old)] or pb["ideas"]
        pick = pool[(i + 1) % len(pool)]
        plan.entries[i].update(topic=pick["topic"], hook=pick["hook"], source="andoza")
        plan.save(update_fields=["entries"])
    return True


def validate_entry(platform: str, e: dict) -> dict:
    """Foydalanuvchi tahriridan keyin qatorni toza holatga keltiradi."""
    allowed = PLATFORM_FORMATS[platform]
    if e.get("format") not in allowed:
        e["format"] = allowed[0]
    for k, mx in (("topic", 200), ("hook", 200), ("cta", 160), ("goal", 80), ("brief", 400)):
        e[k] = (e.get(k) or "").strip()[:mx]
    try:
        d = date.fromisoformat(str(e.get("date")))
        e["weekday"] = WEEKDAYS_UZ[d.weekday()]
    except ValueError:
        e["date"] = ""
    if not re.match(r"^\d{2}:\d{2}$", str(e.get("time") or "")):
        e["time"] = PUBLISH_TIME[platform].strftime("%H:%M")
    return e


def load_to_calendar(plan: ContentPlan, user=None) -> int:
    """Hali yuklanmagan qatorlarni kalendarga QORALAMA qilib qo'shadi (qayta bosganda takror yaratmaydi)."""
    from apps.connections.models import SocialAccount
    from apps.content.models import ContentItem, ContentTarget
    accs = list(SocialAccount.objects.filter(business=plan.business, platform=plan.platform, status="active", archived_at__isnull=True))
    n = 0
    for e in plan.entries:
        if e.get("item_id") or not e.get("date") or not e.get("topic"):
            continue
        d = date.fromisoformat(e["date"])
        hh, mm = (int(x) for x in (e.get("time") or "19:00").split(":"))
        when = datetime.combine(d, time(hh, mm), tzinfo=tz())
        brief = e.get("brief", "")
        extra = []
        if e.get("carousel_id"):
            extra.append(f"Karusel ssenariysi tayyor (#{e['carousel_id']}).")
        if e.get("script_id"):
            extra.append(f"Video ssenariy tayyor (#{e['script_id']}).")
        item = ContentItem.objects.create(
            business=plan.business, title=e["topic"][:200], text="", media_type=e["format"], status="draft", scheduled_at=when, plan=plan,
            hook_idea=(e.get("hook") or "")[:300], cta=(e.get("cta") or "")[:200], goal=(e.get("goal") or "")[:100], created_by=user, ai_draft=True,
            brief=(brief + (" " if brief and extra else "") + " ".join(extra)).strip(), notes=f"Reja ({e.get('pillar_name', '')}). Hook: {e.get('hook', '')}")
        for a in accs[:1]:
            ContentTarget.objects.create(item=item, account=a)
        e["item_id"] = item.pk
        n += 1
    plan.loaded_to_calendar = all(e.get("item_id") for e in plan.entries if e.get("topic"))
    plan.save(update_fields=["entries", "loaded_to_calendar"])
    return n
