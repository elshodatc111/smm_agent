"""Karusel ssenariy generatori.

Karusel — shu biznesga asoslangan KICHIK HIKOYA: qahramon (odatiy mijoz), muammo, burilish, yechim, natija, CTA.
Har slaydda juda qisqa matn (sarlavha ≤6 so'z, matn ≤18 so'z) + dizayner uchun vizual vazifa.
Slayd soni qotirilmagan: hikoya hajmiga qarab 4–30 ta; ko'p bo'lsa teng qismlarga (1-qism, 2-qism, …) bo'linadi,
har qismda ko'pi bilan 10 ta slayd (Instagram karuseli chegarasi). Kontent tili — faqat o'zbek (lotin).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta

from apps.ai_router.router import generate
from apps.ai_router.types import TaskType
from apps.businesses.playbooks import playbook_for
from apps.core.utils import tz

from .models import Carousel
from .planner import is_uzbek_latin

J = {"json": True}
MAX_PART = 10          # bitta postdagi slaydlar chegarasi (rules.py: 2–10)
MIN_SLIDES, MAX_SLIDES = 3, 30
TITLE_WORDS, TEXT_WORDS = 6, 18

SIZES = [("auto", "Avtomatik (hikoyaga qarab)"), ("short", "Qisqa: 5–7 slayd"), ("medium", "O'rta: 8–12 slayd (kerak bo'lsa 2 qism)"),
         ("long", "Katta: 13–20 slayd (2 qism)"), ("xl", "Juda katta: 21–30 slayd (3 qism)")]
SIZE_HINT = {
    "auto": "Slayd sonini hikoyaning o'zi belgilasin: oddiy mavzu uchun 5–8, boy hikoya uchun 12–20 gacha. Bo'sh to'ldirish uchun slayd qo'shma.",
    "short": "Aniq 5–7 ta slayd.", "medium": "Aniq 8–12 ta slayd.", "long": "Aniq 13–20 ta slayd.", "xl": "Aniq 21–30 ta slayd.",
}

ROLE_UZ = {"hook": "Muqova (hook)", "muammo": "Muammo", "oqibat": "Oqibat", "burilish": "Burilish", "yechim": "Yechim", "natija": "Natija",
           "cta": "Harakatga chaqiriq", "qadam": "Qadam", "xato": "Xato", "mif": "Mif", "haqiqat": "Haqiqat", "tavsiya": "Tavsiya",
           "xulosa": "Xulosa", "dalil": "Dalil", "sahna": "Sahna", "maslahat": "Maslahat"}


def _words(s: str, mx: int) -> str:
    w = str(s or "").split()
    if len(w) <= mx:
        return " ".join(w)
    cut = " ".join(w[:mx])
    # imkon bo'lsa gap oxirida to'xtatamiz
    m = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    return cut[: m + 1] if m > len(cut) * 0.5 else cut.rstrip(",;:—-") + "…"


def split_counts(n: int, maxp: int = MAX_PART) -> list[int]:
    """n ta slaydni teng qismlarga bo'ladi: 16 → [8, 8], 11 → [6, 5], 21 → [7, 7, 7]."""
    if n <= maxp:
        return [n]
    k = -(-n // maxp)
    base, extra = divmod(n, k)
    return [base + (1 if i < extra else 0) for i in range(k)]


def clean_slides(raw) -> list[dict]:
    out = []
    for s in raw or []:
        if not isinstance(s, dict):
            continue
        title, text = _words(s.get("title"), TITLE_WORDS), _words(s.get("text"), TEXT_WORDS)
        if not (title or text):
            continue
        role = str(s.get("role") or "").strip().lower()[:20]
        out.append({"role": role, "title": title, "text": text, "visual": str(s.get("visual") or "").strip()[:300],
                    "note": str(s.get("note") or "").strip()[:200]})
    out = out[:MAX_SLIDES]
    for i, s in enumerate(out, 1):
        s["n"] = i
    return out


def build_parts(title: str, slides: list[dict], caption: str, hashtags: list[str], *, start: date | None = None, platform: str = "instagram") -> list[dict]:
    counts = split_counts(len(slides))
    N = len(counts)
    parts, pos = [], 0
    start = start or (datetime.now(tz()).date() + timedelta(days=1))
    for k, c in enumerate(counts, 1):
        nums = [s["n"] for s in slides[pos:pos + c]]
        pos += c
        head = f"{title} — {k}-qism" if N > 1 else title
        cap = caption.strip()
        if N > 1:
            tail = (f"\n\n📖 {k}/{N}-qism. Davomi keyingi postda — kuzatib boring!" if k < N
                    else f"\n\n📖 {k}/{N}-qism (yakun). Oldingi qismlar profilimizda.")
            cap = (caption.strip() or title) + tail
        parts.append({
            "n": k, "of": N, "title": head, "slides": nums, "caption": cap, "hashtags": hashtags,
            "overlay_first": (f"{k}-qism · {N} tadan" if N > 1 else ""),
            "overlay_last": ("Davomi keyingi postda →" if k < N else ""),
            "when": (start + timedelta(days=k - 1)).isoformat(), "item_id": None,
        })
    return parts


def _prompt(business, topic: str, size: str, angle: str, extra: str, platform: str) -> str:
    from apps.businesses import passport
    pb = playbook_for(business)
    angles = "; ".join(f"{a['name']} ({' → '.join(a['arc'])})" for a in pb["angles"])
    return (
        f"Sen {business.name} biznesi uchun karusel (suratlar to'plami) SSENARIYSINI yozayotgan SMM-hikoyachi va art-direktorsan.\n\n"
        f"BIZNES PASPORTI:\n{passport.brief(business, 2400)}\n\n"
        f"MAVZU: {topic}\n"
        f"Hikoya yo'li (tavsiya, kerak bo'lsa moslashtir): {angle or angles}\n"
        f"Qo'shimcha istak: {extra or '—'}\n"
        f"Taqiqlar: {', '.join(pb.get('avoid', []))}\n\n"
        "VAZIFA: shu biznesga xos KICHIK HIKOYA yoz (to'liq hikoya emas — qisqa matnli kadrlar): qahramon shu biznesning haqiqiy mijozi, "
        "aniq vaziyat, muammo, burilish, biznes yordami, natija, oxirida bitta CTA. Umumiy gaplar emas, shu biznesning xizmati, sohasi va mijoz og'rig'iga bog'langan tafsilotlar bo'lsin.\n"
        f"SLAYD SONI: {SIZE_HINT.get(size, SIZE_HINT['auto'])} Slayd soni qotirilmagan; ko'p bo'lsa keyin 2–3 postga bo'linadi, "
        "shuning uchun hikoya boshidan oxirigacha bir butun va har bo'lak oxirida qiziqarli joy bo'lsin.\n"
        f"QOIDALAR: har slaydda sarlavha ≤{TITLE_WORDS} so'z, matn ≤{TEXT_WORDS} so'z (qisqa, ritmik); birinchi slayd — kuchli hook; oxirgi slayd — CTA; "
        "har slayd uchun 'visual' — dizayner nimani chizishi/qanday rasm qo'yishi (kompozitsiya, rang, ob'ekt) 1-2 jumlada; 'role' — hook|muammo|oqibat|burilish|yechim|dalil|natija|qadam|xato|maslahat|cta.\n"
        'JSON: {"title":"hikoya nomi","logline":"1 jumla: hikoya nima haqida","hero":"qahramon kim","angle":"hikoya yo\'li nomi",'
        '"size_reason":"nega aynan shuncha slayd","slides":[{"role":"","title":"","text":"","visual":"","note":"dizayner uchun izoh (ixtiyoriy)"}],'
        '"caption":"post matni 3-6 qator, oxirida CTA","hashtags":["#"],"style":{"palette":"3-4 rang","font":"shrift uslubi","layout":"maket qoidasi","mood":"kayfiyat"}}\n'
        "TIL: faqat o'zbek tili, lotin yozuvida; kirill, rus va ingliz so'zlari yo'q (brend nomi bundan mustasno). "
        "Aniq narx, telefon, foiz, natija raqamini o'ylab topma — kerak bo'lsa [to'ldiring] deb yoz. Bu TAKLIF: egasi tahrirlaydi."
        f" Platforma: {platform}.")


def _fallback(business, topic: str, angle_name: str = "") -> dict:
    """AI ishlamaganda: andozadagi hikoya yo'lidan qisqa skelet (egasi to'ldiradi)."""
    pb = playbook_for(business)
    ang = next((a for a in pb["angles"] if a["name"] == angle_name), pb["angles"][0])
    short = {"hook": ("Bu savol hammada bor", "Shu mavzuda eng ko'p so'raladigan gap"), "muammo": ("Muammo nimada?", "Mijoz aynan shu joyda qiynaladi: [to'ldiring]"),
             "oqibat": ("Agar e'tibor bermasa", "Vaqt va pul yo'qotiladi: [to'ldiring]"), "burilish": ("Hammasi o'zgardi", "Mijoz bizga murojaat qildi"),
             "yechim": ("Biz nima qildik", "Aniq qadamlar bilan hal qildik: [to'ldiring]"), "natija": ("Natija", "Mijoz kutganiga erishdi: [to'ldiring]"),
             "cta": ("Siz ham boshlang", "Telegramga yozing — maslahat beramiz")}
    slides = []
    for r in ang["arc"]:
        t, x = short.get(r, (ROLE_UZ.get(r, r).capitalize(), "[to'ldiring]"))
        slides.append({"role": r, "title": t if r != "hook" else _words(topic, TITLE_WORDS), "text": x, "visual": "Sodda fon, katta sarlavha, biznesga mos rasm", "note": ""})
    return {"title": _words(topic, 8), "logline": topic, "hero": "Odatiy mijoz", "angle": ang["name"], "slides": slides,
            "caption": f"{topic}\n\nBatafsil ma'lumot uchun yozing.", "hashtags": [], "style": {}}


def generate_carousel(business, topic: str, *, size: str = "auto", angle: str = "", extra: str = "", platform: str = "instagram",
                      user=None, router=None, plan=None, plan_entry: int | None = None) -> Carousel:
    topic = (topic or "").strip() or "Biznesimiz haqida foydali hikoya"
    d, gen, used_ai = None, None, False
    for attempt in range(2):
        try:
            res, gen = generate(TaskType.LONG_UZ, _prompt(business, topic, size, angle, extra + (" Faqat o'zbek lotin!" if attempt else ""), platform),
                                business=business, kind="carousel", user=user, schema=J, router=router)
        except Exception:  # noqa: BLE001
            break
        cand = res.data or {}
        sl = clean_slides(cand.get("slides"))
        blob = json.dumps(cand, ensure_ascii=False)
        if len(sl) >= MIN_SLIDES and is_uzbek_latin(blob):
            d, used_ai = cand, True
            d["slides"] = sl
            break
    if d is None:
        d = _fallback(business, topic, angle)
        d["slides"] = clean_slides(d["slides"])
    tags = [str(h) if str(h).startswith("#") else f"#{h}" for h in (d.get("hashtags") or []) if isinstance(h, str)][:10]
    title = _words(d.get("title") or topic, 10)
    parts = build_parts(title, d["slides"], str(d.get("caption") or ""), tags, platform=platform)
    story = {k: d.get(k, "") for k in ("logline", "hero", "size_reason")}
    story["style"] = d.get("style") if isinstance(d.get("style"), dict) else {}
    story["source"] = "ai" if used_ai else "andoza"
    return Carousel.objects.create(business=business, platform=platform, title=title, topic=topic[:300], angle=str(d.get("angle") or angle)[:80],
                                   story=story, slides=d["slides"], parts=parts, generation=gen, plan=plan, plan_entry=plan_entry, created_by=user)


def rebuild_parts(c: Carousel) -> None:
    """Slaydlar tahrirlangach (qo'shildi/o'chirildi) qismlarni qayta hisoblaydi."""
    for i, s in enumerate(c.slides, 1):
        s["n"] = i
    old = c.parts[0] if c.parts else {}
    cap = old.get("caption", "")
    cap = re.sub(r"\n\n📖.*$", "", cap, flags=re.S)
    c.parts = build_parts(c.title, c.slides, cap, old.get("hashtags", []), platform=c.platform)


def part_slides(c: Carousel, part: dict) -> list[dict]:
    want = set(part["slides"])
    return [s for s in c.slides if s["n"] in want]


def part_text(c: Carousel, part: dict) -> str:
    """Dizayner/Canva uchun nusxa olishga qulay matn."""
    L = [f"{part['title']}  ({len(part['slides'])} ta slayd)"]
    for k, s in enumerate(part_slides(c, part), 1):
        L.append(f"\n{k}-SLAYD · {ROLE_UZ.get(s['role'], s['role'] or '—')}")
        if k == 1 and part.get("overlay_first"):
            L.append(f"  [belgi: {part['overlay_first']}]")
        L.append(f"  Sarlavha: {s['title']}")
        if s["text"]:
            L.append(f"  Matn: {s['text']}")
        L.append(f"  Vizual: {s['visual']}")
        if s.get("note"):
            L.append(f"  Izoh: {s['note']}")
        if k == len(part["slides"]) and part.get("overlay_last"):
            L.append(f"  [belgi: {part['overlay_last']}]")
    L.append(f"\nPOST MATNI:\n{part['caption']}")
    if part.get("hashtags"):
        L.append(" ".join(part["hashtags"]))
    return "\n".join(L)


def style_text(c: Carousel) -> str:
    st = (c.story or {}).get("style") or {}
    return "; ".join(f"{k}: {v}" for k, v in (("Ranglar", st.get("palette")), ("Shrift", st.get("font")), ("Maket", st.get("layout")), ("Kayfiyat", st.get("mood"))) if v)


def regen_slide(c: Carousel, n: int, instruction: str = "", user=None, router=None) -> bool:
    """Bitta slaydni qayta yozadi (qisqaroq/boshqacha)."""
    if not (1 <= n <= len(c.slides)):
        return False
    s = c.slides[n - 1]
    around = [{"n": x["n"], "title": x["title"], "text": x["text"]} for x in c.slides]
    prompt = (f"Karusel hikoyasi: {c.title}. Biznes: {c.business.name}. Barcha slaydlar: {json.dumps(around, ensure_ascii=False)}\n"
              f"{n}-slaydni qayta yoz (rol: {s['role']}). Istak: {instruction or 'qisqaroq va kuchliroq'}. "
              f"Sarlavha ≤{TITLE_WORDS} so'z, matn ≤{TEXT_WORDS} so'z; hikoya izchilligini buzma. Faqat o'zbek lotin. "
              'JSON: {"title":"","text":"","visual":""}')
    try:
        res, _ = generate(TaskType.LONG_UZ, prompt, business=c.business, kind="carousel", user=user, schema=J, router=router)
    except Exception:  # noqa: BLE001
        return False
    d = res.data or {}
    new = clean_slides([{**s, **{k: d.get(k) for k in ("title", "text", "visual") if d.get(k)}}])
    if not new or not is_uzbek_latin(json.dumps(d, ensure_ascii=False)):
        return False
    new[0]["n"] = n
    c.slides[n - 1] = new[0]
    c.save(update_fields=["slides"])
    return True


def load_part_to_calendar(c: Carousel, k: int, user=None) -> int | None:
    """k-qismni kalendarga QORALAMA karusel post qilib qo'shadi. Qaytaradi: ContentItem.pk."""
    from apps.connections.models import SocialAccount
    from apps.content.models import ContentItem, ContentTarget
    part = next((p for p in c.parts if p["n"] == k), None)
    if not part or part.get("item_id"):
        return None
    when = datetime.combine(date.fromisoformat(part["when"]), time(19, 0), tzinfo=tz())
    text = part["caption"] + ("\n\n" + " ".join(part["hashtags"]) if part.get("hashtags") else "")
    item = ContentItem.objects.create(business=c.business, title=part["title"][:200], text=text, media_type="carousel", status="draft",
                                      scheduled_at=when, brief=part_text(c, part), created_by=user, ai_draft=True,
                                      notes=f"Karusel ssenariysi #{c.pk}, {k}/{len(c.parts)}-qism. Uslub: {style_text(c)}")
    acc = SocialAccount.objects.filter(business=c.business, platform=c.platform, status="active", archived_at__isnull=True).first()
    if acc:
        ContentTarget.objects.create(item=item, account=acc)
    part["item_id"] = item.pk
    c.save(update_fields=["parts"])
    return item.pk
