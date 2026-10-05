"""G'oyalar banki: raqobatchi va o'z tahlilidan har kuni kamida bitta g'oya + har bir g'oya uchun rejissyor ssenariysi."""
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

from django.utils import timezone

from apps.core.notify import notify
from apps.core.settings_store import get_setting
from apps.core.utils import tz

from .models import Idea

log = logging.getLogger(__name__)
FMT_MAP = {"reel": "reel", "short": "short", "video": "video", "story": "story", "carousel": "carousel", "image": "post", "album": "carousel", "text": "post", "post": "post"}
FMT_UZ = {"post": "Post", "reel": "Reels", "short": "Shorts", "video": "Video", "story": "Stories", "carousel": "Karusel"}

EVERGREEN = [
    ("Savol-javob: mijozlar eng ko'p so'raydigan 3 savol", "carousel", "Mijozlar doim so'raydigan savollarga qisqa, aniq javoblar. Saqlashlar va izohlarni oshiradi.", "Bizdan eng ko'p so'raladigan 3 ta savol — javoblari shu yerda"),
    ("Jarayon ortida: mahsulot/xizmat qanday tayyorlanadi", "reel", "Kamera ortidagi jarayon ishonchni oshiradi va ko'rishlarni tortadi.", "Buni hech kim ko'rsatmaydi — bizda shunday tayyorlanadi"),
    ("Mif va haqiqat: sohangizdagi 3 ta keng tarqalgan xato", "reel", "Xatolarni tuzatish ekspert obro'sini beradi.", "Bu 3 ta gapning hammasi noto'g'ri"),
    ("Mijoz natijasi: oldin va keyin", "carousel", "Real natija eng kuchli ijtimoiy isbot.", "Mijozimiz 30 kunda shunday natijaga erishdi"),
    ("Narx qanday shakllanadi? Shaffof tushuntirish", "reel", "Narx haqidagi savollar eng ko'p sotuvga yaqin.", "Narx nima uchun shunday? Hisoblab ko'rsatamiz"),
    ("Xodim bilan qisqa tanishuv", "story", "Inson yuzi brendni yaqinlashtiradi.", "Tanishing: bizning jamoadan"),
    ("Xato qilmang: yangi mijozlar eng ko'p yo'l qo'yadigan xato", "reel", "Foydali ogohlantirish saqlanadi va ulashiladi.", "Bu xatoni qilmang — ko'pchilik shunda adashadi"),
]


def _first_line(t: str, n: int = 140) -> str:
    t = (t or "").strip().split("\n")[0].strip()
    return t[:n]


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", (s or "").lower()).strip()[:80]


def signals(business, days: int = 30) -> dict:
    from apps.metrics import analytics as an
    from apps.metrics.models import CompetitorPost
    since = timezone.now() - timedelta(days=days)
    comp = []
    for cp in CompetitorPost.objects.filter(business_id=business.pk, published_at__gte=since).select_related("competitor").order_by("-views", "-likes")[:12]:
        if not (cp.text or "").strip():
            continue
        comp.append({"id": cp.pk, "competitor": cp.competitor.name or cp.competitor.handle, "platform": cp.competitor.platform, "type": cp.media_type or "post",
                     "text": (cp.text or "")[:220], "views": cp.views, "likes": cp.likes, "comments": cp.comments})
    own = []
    try:
        for r in an.top_posts(business, 5, days=60):
            own.append({"text": (r.post.text or "")[:160], "type": r.post.media_type, "platform": r.post.platform, "er": r.er})
    except Exception:  # noqa: BLE001
        pass
    try:
        types = an.by_type(business)
    except Exception:  # noqa: BLE001
        types = []
    return {"competitor_top": comp, "own_top": own, "types": types}


def _recent_keys(business, days: int = 60) -> tuple[set, set]:
    since = timezone.now() - timedelta(days=days)
    titles, posts = set(), set()
    for i in Idea.objects.filter(business=business, created_at__gte=since).exclude(status="rejected"):
        titles.add(_norm(i.title))
        if (i.source_ref or {}).get("post_id"):
            posts.add(i.source_ref["post_id"])
    return titles, posts


def _accounts_platforms(business) -> list[str]:
    return sorted({a.platform for a in business.accounts.filter(archived_at__isnull=True)}) or ["instagram"]


def heuristic(business, sig: dict, n: int, day) -> list[dict]:
    titles, used_posts = _recent_keys(business)
    out = []
    for c in sig["competitor_top"]:
        if len(out) >= n:
            break
        if c["id"] in used_posts:
            continue
        hook = _first_line(c["text"], 110)
        t = f"«{hook[:60]}» mavzusida o'z versiyamiz"
        if _norm(t) in titles:
            continue
        nums = ", ".join(x for x in (f"{c['views']} ko'rish" if c["views"] else "", f"{c['likes']} layk" if c["likes"] else "", f"{c['comments']} izoh" if c["comments"] else "") if x)
        out.append({"title": t, "platform": c["platform"], "fmt": FMT_MAP.get(c["type"], "post"), "source": "competitor",
                    "angle": f"Raqobatchi ({c['competitor']}) shu mavzudagi posti yaxshi natija bergan" + (f" ({nums})" if nums else "") + ". Nusxa ko'chirmasdan, o'z tajribangiz, aniq raqam yoki mijoz misoli bilan boshqa burchakdan ayting.",
                    "hook": hook, "why": f"Raqobatchi posti auditoriyada qiziqish uyg'otgan: {nums or 'yaxshi natija'}. Shu mavzuni o'z ovozingiz bilan oling.",
                    "source_ref": {"competitor": c["competitor"], "post_id": c["id"], "views": c["views"], "likes": c["likes"], "text": c["text"][:160]}})
    pls = _accounts_platforms(business)
    if len(out) < n:
        for o in sig["own_top"]:
            if len(out) >= n:
                break
            hook = _first_line(o["text"], 100)
            t = f"Yaxshi ishlagan mavzuning davomi: «{hook[:55]}»"
            if not hook or _norm(t) in titles:
                continue
            out.append({"title": t, "platform": o["platform"], "fmt": FMT_MAP.get(o["type"], "post"), "source": "own",
                        "angle": "O'z postingiz yaxshi natija bergan. Shu mavzuni yangi burchakdan davom ettiring: 2-qism, savol-javob yoki mijoz fikri.",
                        "hook": "Ko'pchilik so'radi — davomi shu yerda: " + hook[:70], "why": "O'z tahlilingizda bu post eng yuqori ER olgan; ishlagan formulani takrorlash xavfsiz.",
                        "source_ref": {"own_text": o["text"][:140], "er": o["er"]}})
    k = day.toordinal()
    j = 0
    while len(out) < n and j < len(EVERGREEN) * 2:
        t, f, a, h = EVERGREEN[(k + j) % len(EVERGREEN)]
        j += 1
        if _norm(t) in titles:
            continue
        out.append({"title": t, "platform": pls[(k + j) % len(pls)], "fmt": f, "source": "auto", "angle": a, "hook": h,
                    "why": "Doimiy ishlaydigan g'oya (tahlil ma'lumoti yetarli bo'lmaganda taklif qilinadi).", "source_ref": {}})
    return out[:n]


def ai_ideas(business, sig: dict, n: int, router=None) -> list[dict]:
    from apps.ai_router.router import generate
    from apps.ai_router.types import TaskType
    titles, used_posts = _recent_keys(business)
    prompt = (f"Sen SMM strategsan. Quyidagi RAQOBATCHILAR va O'Z tahlili asosida {n} ta yangi kontent g'oyasi o'ylab top. Raqobatchini nusxalama — faqat mavzu/burchakni ol "
              f"va biznesga moslab boshqacha yoz. Oldin berilgan g'oyalarni takrorlama: {sorted(titles)[:15]}.\n"
              'JSON: {"ideas":[{"title":"","platform":"telegram|instagram|youtube","fmt":"post|reel|short|video|story|carousel","angle":"g\'oya mohiyati 2 gap","hook":"birinchi jumla",'
              '"why":"qaysi raqam/tahlilga tayanadi","source_post_id":null}]}\n'
              f"Biznes: {business.name}; faoliyat: {business.industry}; auditoriya: {business.audience}; platformalar: {_accounts_platforms(business)}\n"
              f"Raqobatchi top postlari (id bilan): {json.dumps(sig['competitor_top'][:8], ensure_ascii=False, default=str)}\n"
              f"O'z top postlari: {json.dumps(sig['own_top'][:5], ensure_ascii=False, default=str)}\nFormatlar: {json.dumps(sig['types'], ensure_ascii=False, default=str)[:600]}")
    res, _ = generate(TaskType.LONG_UZ, prompt, business=business, kind="ideas", schema={"json": True}, router=router)
    out = []
    comp_by_id = {c["id"]: c for c in sig["competitor_top"]}
    for d in (res.data or {}).get("ideas", [])[:n]:
        if not isinstance(d, dict) or not d.get("title"):
            continue
        sp = d.get("source_post_id")
        c = comp_by_id.get(sp) if isinstance(sp, int) else None
        out.append({"title": str(d["title"])[:200], "platform": d.get("platform") if d.get("platform") in ("telegram", "instagram", "youtube") else (c["platform"] if c else _accounts_platforms(business)[0]),
                    "fmt": FMT_MAP.get(d.get("fmt", "post"), "post"), "angle": str(d.get("angle", "")), "hook": str(d.get("hook", ""))[:300], "why": str(d.get("why", "")),
                    "source": "competitor" if c else "own", "source_ref": ({"competitor": c["competitor"], "post_id": c["id"], "views": c["views"], "likes": c["likes"], "text": c["text"][:160]} if c else {})})
    return out


def heuristic_script(idea: Idea) -> dict:
    h = idea.hook or idea.title
    tall = idea.fmt in ("reel", "short", "story")
    return {"title": idea.title, "concept": idea.angle, "hook_variants": [h, "Bir daqiqa ajrating — " + h[:70]], "duration_sec": 30 if tall else 0,
            "location": "Ish joyingiz yoki mahsulot/xizmat ko'rinib turgan joy, yorug' joy (deraza yonida)",
            "cast": [{"role": "Boshlovchi (siz yoki xodim)", "look": "Toza, brend ranglariga mos kiyim", "note": "Kameraga qarab, iliq va ishonchli gapiring"}],
            "equipment": ["Telefon: 9:16, 1080p, 30fps", "Shtativ yoki qo'l bilan tekis ushlash", "Tabiiy yoki yumshoq yorug'lik", "Yoqali mikrofon (bo'lsa)"],
            "audio": {"voice_style": "Tabiiy, o'rtacha tezlik, jumlalar qisqa", "music_mood": "Yengil, motivatsion, 100-110 BPM (ovozdan past)", "trending_audios": [], "sfx": ["yengil 'whoosh' o'tishlarda"]},
            "scenes": [
                {"n": 1, "t": "0-3s", "shot_type": "close-up", "camera": {"position": "Aktyordan 1 m old tomonda, ko'z darajasida", "angle": "ko'z darajasi", "movement": "qimirlamaydi", "orientation": "vertikal 9:16"},
                 "actor": {"action": "Kameraga qaraydi va hookni aytadi", "emotion": "qiziquvchan, jiddiy", "line": h}, "voiceover": "", "on_screen_text": h[:60], "audio_cue": "musiqa boshlanadi", "transition": "tezkor kesish"},
                {"n": 2, "t": "3-12s", "shot_type": "medium", "camera": {"position": "Aktyorning o'ng tomonida 1.5 m, ko'krak balandligida", "angle": "ko'z darajasi", "movement": "sekin yaqinlashadi", "orientation": "vertikal 9:16"},
                 "actor": {"action": "Asosiy fikrni tushuntiradi: " + (idea.angle[:120] or idea.title), "emotion": "ishonchli", "line": ""}, "voiceover": "", "on_screen_text": "Asosiy fikr", "audio_cue": "musiqa pasayadi", "transition": "kesish"},
                {"n": 3, "t": "12-24s", "shot_type": "detail", "camera": {"position": "Mahsulot/jarayonga yaqin, yuqoridan 45°", "angle": "yuqori", "movement": "qo'lda, sekin", "orientation": "vertikal 9:16"},
                 "actor": {"action": "Misol yoki isbot ko'rsatadi (raqam, natija, mijoz fikri)", "emotion": "xotirjam", "line": ""}, "voiceover": "Aniq misol keltiring", "on_screen_text": "Isbot", "audio_cue": "", "transition": "kesish"},
                {"n": 4, "t": "24-30s", "shot_type": "close-up", "camera": {"position": "1 m old tomonda, ko'z darajasida", "angle": "ko'z darajasi", "movement": "qimirlamaydi", "orientation": "vertikal 9:16"},
                 "actor": {"action": "Chaqiriq aytadi va kameraga qaraydi", "emotion": "iliq tabassum", "line": "Saqlab qo'ying va do'stingizga yuboring"}, "voiceover": "", "on_screen_text": "Saqlang / yozing", "audio_cue": "musiqa yakunlanadi", "transition": ""}],
            "cta": "Yozing yoki bog'laning — havola/telefon matnda", "props": [], "editing_notes": ["CapCut: avtosubtitr yoqing", "Birinchi 3 soniyada matn va harakat bo'lsin", "Har 3-4 soniyada kesish"],
            "publishing": {"caption_hint": idea.angle[:150], "hashtags": [], "best_time": ""}, "checklist": ["Ovoz tiniqligi", "Yorug'lik yetarli", "Telefon 9:16 vertikal", "Logo/telefon ko'rinadimi"], "notes": "Bu andoza ssenariy. AI ulangan bo'lsa «AI bilan to'liq ssenariy» tugmasi aniq kamera/aktyor ko'rsatmalarini yozadi."}


def make_script(idea: Idea, use_ai: bool = True, user=None, router=None) -> Idea:
    from . import services
    body = None
    if use_ai:
        try:
            from apps.ai_router.router import generate
            from apps.ai_router.types import TaskType
            prompt = (f"{idea.get_fmt_display() if hasattr(idea, 'get_fmt_display') else idea.fmt} formatida video ssenariy yoz.\nG'OYA: {idea.title}\nMOHIYAT: {idea.angle}\nHOOK: {idea.hook}\n"
                      f"NEGA: {idea.why}\nPlatforma: {idea.platform}\nBiznes: {idea.business.name}; {idea.business.industry}\n{services.DIRECTOR_SCHEMA}")
            res, _ = generate(TaskType.LONG_UZ, prompt, business=idea.business, kind="idea_script", user=user, schema={"json": True}, router=router)
            if res.data and res.data.get("scenes"):
                body = res.data
        except Exception as e:  # noqa: BLE001
            log.info("G'oya ssenariysi AI bilan yaratilmadi: %s", str(e)[:160])
    ai_ok = body is not None
    body = body or heuristic_script(idea)
    idea.script = body
    idea.script_text = services.script_text(body)
    idea.save(update_fields=["script", "script_text"])
    idea.ai_script = ai_ok  # type: ignore[attr-defined]
    return idea


def create_ideas(business, items: list[dict], day, with_ai_script: bool = True) -> list[Idea]:
    out = []
    for d in items:
        idea = Idea.objects.create(business=business, title=d["title"], platform=d.get("platform", ""), fmt=d.get("fmt", ""), angle=d.get("angle", ""), hook=d.get("hook", ""),
                                   why=d.get("why", ""), source=d.get("source", "auto"), source_ref=d.get("source_ref") or {}, day=day)
        make_script(idea, use_ai=with_ai_script)
        out.append(idea)
    return out


def generate_for_business(business, n: int = 1, day=None, use_ai: bool = True) -> list[Idea]:
    day = day or timezone.localtime(timezone.now(), tz()).date()
    sig = signals(business)
    items: list[dict] = []
    if use_ai:
        try:
            items = ai_ideas(business, sig, n)
        except Exception as e:  # noqa: BLE001
            log.info("AI g'oya bermadi, tahlil asosida yaratiladi: %s", str(e)[:160])
    if len(items) < n:
        have = {_norm(i["title"]) for i in items}
        items += [h for h in heuristic(business, sig, n - len(items) + 2, day) if _norm(h["title"]) not in have][: n - len(items)]
    return create_ideas(business, items[:n], day, with_ai_script=use_ai)


def ensure_daily(business, user=None) -> list[Idea]:
    """Bugun uchun kamida N ta g'oya borligini ta'minlaydi (sozlama: ideas.per_day, odatda 1)."""
    day = timezone.localtime(timezone.now(), tz()).date()
    want = int(get_setting("ideas.per_day", 1))
    have = Idea.objects.filter(business=business, day=day).count()
    if have >= want or not get_setting("ideas.daily_enabled", True):
        return []
    new = generate_for_business(business, want - have, day)
    for i in new:
        notify("idea.new", f"Yangi g'oya: {i.title[:80]}", (i.angle or "")[:240] + "\n(Ssenariysi tayyor — G'oyalar bankida.)", business_id=business.pk,
               link=f"/goyalar/{i.pk}/", dedupe_key=f"idea:{i.pk}")
    return new
