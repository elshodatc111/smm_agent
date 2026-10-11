"""AI studiya xizmatlari: brend profili, kontent-plan, ssenariy, caption, izoh, 'nega ishladi', hook."""
from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import date, datetime, time


from apps.ai_router.router import AIRouter, generate
from apps.ai_router.types import TaskType
from apps.businesses.services import save_brand_version
from apps.core.notify import notify
from apps.core.utils import tz

from .models import (ContentPlan, Hook, PostInsight, Script, ScriptAnalysis)

J = {"json": True}  # response_schema belgisi: JSON kutiladi

# AI faqat TAKLIF beradi: egasi o'zi yozadi/tahrirlaydi. Platforma AI matnini o'zi nashr qilmaydi.
SUGGEST_ONLY = (" MUHIM: bu faqat TAKLIF/qoralama g'oya. Biznes egasi uni o'zi qayta yozib, o'z ovozida chiqaradi: "
                "aniq narx, telefon, va'da yoki raqamlarni o'ylab topma; o'rniga [to'ldiring] belgisini qo'y.")


def _biz_brief(b) -> str:
    return (f"Nomi: {b.name}\nFaoliyat: {b.industry}\nHudud: {b.region}\nTil: {b.languages}\nTavsif: {b.description}\n"
            f"Mahsulot/xizmatlar: {b.products}\nNarx oralig'i: {b.price_range}\nAuditoriya: {b.audience}\n"
            f"Asosiy maqsad: {b.get_main_goal_display()}\nAloqa: {b.contact_info}")


def generate_brand_profile(business, user=None, router: AIRouter | None = None):
    tpl = business.template.config if business.template else {}
    prompt = (f"Quyidagi biznes uchun BREND PROFILI (system prompt) yoz. JSON qaytar: "
              f'{{"prompt": "<AI uchun to\'liq yo\'riqnoma matni o\'zbekcha>", "tone": "", "usp": "", "banned_words": [], '
              f'"hashtags": [], "cta_style": "", "audience_portrait": "", "pillars": []}}\n\nBIZNES:\n{_biz_brief(business)}\n'
              f"ANDOZA MASLAHATI: {json.dumps(tpl, ensure_ascii=False)}")
    res, gen = generate(TaskType.BRAND_PROFILE, prompt, business=None, kind="brand_profile", user=user, schema=J, router=router)
    d = res.data or {}
    content = d.get("prompt") or res.text or ""
    bp = save_brand_version(business, content, user=user, structured={k: v for k, v in d.items() if k != "prompt"},
                            note="AI yozdi — ko'rib chiqing va tasdiqlang", ai=True)
    return bp


def why_worked(post, user=None, router=None) -> PostInsight:
    from apps.metrics.analytics import is_winner, median_baseline, numeric_basis
    nums = numeric_basis(post)
    last = post.history.order_by("-taken_at").first()
    verdict = "weak"
    if last:
        base = median_baseline(post.business)
        verdict = "winner" if is_winner(last, base) else ("average" if nums.get("er_nisbati") and nums["er_nisbati"] >= 0.8 else "weak")
    prompt = ("Post nima uchun shunday natija berganini RAQAMLARGA tayanib tushuntir. Faqat quyidagi raqamlarni ishlat. "
              'JSON: {"reasons":["..."],"repeat":["takrorlash tavsiyasi"],"change":["nimani o\'zgartirish"],"summary":"2 gap"}\n'
              f"Post matni: {post.text[:600]}\nRaqamlar: {json.dumps(nums, ensure_ascii=False, default=str)}\nBaho: {verdict}")
    res, gen = generate(TaskType.WHY_WORKED, prompt, business=post.business, kind="why_worked", user=user, schema=J, router=router)
    d = res.data or {}
    return PostInsight.objects.create(post=post, numbers=nums, verdict=verdict, text=d.get("summary", res.text or ""), data=d, generation=gen)


def monthly_plan(business, platform: str, month: date, user=None, router=None) -> ContentPlan:
    from apps.metrics.analytics import best_times, by_type, top_posts
    tops = [{"matn": r.post.text[:120], "tur": r.post.media_type, "er": r.er} for r in top_posts(business, 5)]
    ctx = {"eng_yaxshi_postlar": tops, "turlar": by_type(business), "vaqtlar": best_times(business)}
    comp = []
    from apps.metrics.models import CompetitorPost
    for cp in CompetitorPost.objects.filter(business_id=business.pk).order_by("-views")[:5]:
        comp.append(cp.text[:100])
    tpl = business.template.config if business.template else {}
    days = monthrange(month.year, month.month)[1]
    prompt = (f"{month:%Y-%m} oyi uchun {platform} kontent-planini tuz. Oyda {days} kun. Haftasiga 3-5 post. "
              'JSON: {"summary":"qisqa strategiya","entries":[{"date":"YYYY-MM-DD","format":"post|reel|short|video|story|carousel","topic":"","hook":"","cta":"","goal":"","role":"smm|kontent-maker"}]}\n'
              f"Tahlil: {json.dumps(ctx, ensure_ascii=False, default=str)[:3000]}\nRaqobatchi g'oyalari (nusxa ko'chirma): {comp}\n"
              f"Andoza: {json.dumps(tpl, ensure_ascii=False)[:800]}")
    res, gen = generate(TaskType.LONG_UZ, prompt, business=business, kind="plan", user=user, schema=J, router=router)
    d = res.data or {}
    entries = [e for e in d.get("entries", []) if isinstance(e, dict) and re.match(r"\d{4}-\d{2}-\d{2}$", str(e.get("date", "")))]
    return ContentPlan.objects.create(business=business, platform=platform, month=month.replace(day=1), entries=entries,
                                      summary=d.get("summary", ""), generation=gen, created_by=user)


def load_plan_to_calendar(plan: ContentPlan, user=None) -> int:
    from apps.content.models import ContentItem, ContentTarget
    from apps.connections.models import SocialAccount
    accs = list(SocialAccount.objects.filter(business=plan.business, platform=plan.platform, status="active", archived_at__isnull=True))
    n = 0
    for e in plan.entries:
        d = date.fromisoformat(e["date"])
        fmt = {"post": "image", "reel": "reel", "short": "short", "video": "video", "story": "story", "carousel": "carousel"}.get(e.get("format", "post"), "image")
        when = datetime.combine(d, time(19, 0), tzinfo=tz())
        item = ContentItem.objects.create(business=plan.business, title=(e.get("topic") or "Reja")[:200], text="", media_type=fmt,
                                          status="draft", scheduled_at=when, plan=plan, hook_idea=e.get("hook", "")[:300],
                                          cta=e.get("cta", "")[:200], goal=e.get("goal", "")[:100], created_by=user, ai_draft=True,
                                          notes=f"Reja: {e.get('hook', '')}")
        for a in accs[:1]:
            ContentTarget.objects.create(item=item, account=a)
        n += 1
    plan.loaded_to_calendar = True
    plan.save(update_fields=["loaded_to_calendar"])
    return n


DIRECTOR_SCHEMA = (
    'JSON: {"title":"","concept":"1-2 gap g\'oya","hook_variants":["A","B"],"duration_sec":30,'
    '"location":"qayerda suratga olinadi","cast":[{"role":"aktyor/boshlovchi","look":"kiyim, ko\'rinish","note":""}],'
    '"equipment":["telefon sozlamasi: 9:16, 1080p/4K, 30fps","shtativ","yorug\'lik","mikrofon"],'
    '"audio":{"voice_style":"ovoz ohangi va tezligi","music_mood":"musiqa kayfiyati va tempi (BPM)",'
    '"trending_audios":[{"name":"audio nomi — ijrochi","why":"nega mos","where":"Instagram Reels / TikTok trend"}],"sfx":["ovoz effekti"]},'
    '"scenes":[{"n":1,"t":"0-3s","shot_type":"close-up|medium|wide|POV|detail","camera":{"position":"kamera qayerda turadi (aktyorga nisbatan: chap/o\'ng/old/orqa, balandlik, masofa)",'
    '"angle":"past/ko\'z darajasi/yuqori","movement":"qimirlamaydi|sekin yaqinlashadi|yon tomonga yuradi|qo\'lda","orientation":"vertikal 9:16"},'
    '"actor":{"action":"aktyor nima qiladi, qadamma-qadam","emotion":"yuz ifodasi","line":"aytadigan gap (bo\'lsa)"},'
    '"voiceover":"","on_screen_text":"","audio_cue":"shu paytda musiqa/ovoz","transition":"keyingi kadrga o\'tish"}],'
    '"cta":"","props":[],"editing_notes":["CapCut/InShot montaj ko\'rsatmasi"],"publishing":{"caption_hint":"","hashtags":[],"best_time":"HH:MM"},'
    '"checklist":["suratga olishdan oldin tekshirish"],"notes":""}\n'
    "MUHIM: To'liq REJISSYOR sifatida yoz — telefon va aktyor qiynalmasdan, hech narsani o'ylamasdan aynan shu ko'rsatma bo'yicha suratga olsin. "
    "Har sahnada kamera joyi (aktyorning chap/o'ng tomoni, balandligi, masofa metrda), burchagi va harakati, aktyorning harakati va ifodasi aniq bo'lsin. "
    "Trend audio: shu biznes yo'nalishi va platformada hozir ommabop uslubdagi 3-5 ta audio nomini ber, lekin aniq trend ekanini kafolatlama — "
    "'Instagram Reels → Audio → Trending' bo'limidan tekshirishni eslat. Hamma matn o'zbek tilida (lotin).")


def generate_script(business, brief: str, fmt: str, variants: int = 2, user=None, router=None) -> Script:
    hooks = list(Hook.objects.filter(business=business, status="saved").values_list("text", flat=True)[:5])
    from apps.content.insights import insights_brief
    prompt = (f"{fmt} formatida video ssenariy yoz. Qisqa maqsad: {brief}\n"
              f"Biznes yo'nalishi/sohasi: {getattr(business, 'industry', '') or getattr(business, 'description', '') or business.name}\n"
              f"Ilhom uchun hooklar (nusxa ko'chirma, faqat g'oya): {hooks}\n"
              f"Tahlil:\n{insights_brief(business)}\n"
              f"{DIRECTOR_SCHEMA}\nHook variantlari soni: {variants} (A/B).")
    res, gen = generate(TaskType.LONG_UZ, prompt, business=business, kind="script", user=user, schema=J, router=router)
    d = res.data or {}
    return Script.objects.create(business=business, title=d.get("title") or brief[:80], fmt=fmt if fmt in dict(Script.FORMATS) else "reel",
                                 brief=brief, body=d, generation=gen, created_by=user)


def analyze_script(script: Script, user=None, router=None) -> ScriptAnalysis:
    text = script.raw_text or json.dumps(script.body, ensure_ascii=False)
    prompt = ('Ssenariyni baho. Har mezon 0-10: hook, structure, pace, duration_fit, cta, brand_fit, sales. '
              'JSON: {"criteria":{"hook":0,"structure":0,"pace":0,"duration_fit":0,"cta":0,"brand_fit":0,"sales":0},"score":0-100,"fixes":["aniq tuzatish"]}\n'
              f"Format: {script.fmt}\nSsenariy:\n{text[:5000]}")
    res, gen = generate(TaskType.SCRIPT_REVIEW, prompt, business=script.business, kind="script_review", user=user, schema=J, router=router)
    d = res.data or {}
    crit = d.get("criteria", {})
    score = d.get("score")
    if not isinstance(score, (int, float)):
        vals = [v for v in crit.values() if isinstance(v, (int, float))]
        score = round(sum(vals) / len(vals) * 10) if vals else 0
    return ScriptAnalysis.objects.create(script=script, score=int(score), data=d, generation=gen)


def captions(business, topic: str, platform: str, user=None, router=None) -> dict:
    lim = {"instagram": "2200 belgigacha, 5-10 hashtag", "telegram": "1024 belgigacha (media bilan)", "youtube": "sarlavha ≤100, tavsif ≤5000"}.get(platform, "")
    prompt = (f"{platform} uchun mavzu bo'yicha 3 ta caption varianti va hashtaglar yoz. Cheklov: {lim}. "
              f'JSON: {{"variants":["",""],"hashtags":[]}}{SUGGEST_ONLY}\nMavzu: {topic}')
    res, _ = generate(TaskType.LONG_UZ, prompt, business=business, kind="caption", user=user, schema=J, router=router)
    return res.data or {}


def refresh_hook_suggestions(business, limit: int = 10) -> int:
    """O'z va raqobatchi eng yaxshi postlaridan birinchi jumlani 'taklif' hook sifatida qo'shadi (AIsiz)."""
    from apps.metrics.analytics import top_posts
    from apps.metrics.models import CompetitorPost
    n = 0

    def first_line(t):
        t = (t or "").strip().split("\n")[0]
        return t[:200]
    for r in top_posts(business, limit):
        h = first_line(r.post.text)
        if h and not Hook.objects.filter(business=business, text=h).exists():
            Hook.objects.create(business=business, text=h, fmt=r.post.media_type, source="own", status="suggested", post=r.post,
                                result={"views": r.views, "er": r.er}, industry=business.industry)
            n += 1
    for cp in CompetitorPost.objects.filter(business_id=business.pk).exclude(views=None).order_by("-views")[:limit]:
        h = first_line(cp.text)
        if h and not Hook.objects.filter(business=business, text=h).exists():
            Hook.objects.create(business=business, text=h, fmt=cp.media_type, source="competitor", status="suggested",
                                result={"views": cp.views}, industry=business.industry)
            n += 1
    return n


# ---------------- Kontent formasi uchun: tahlilga asoslangan matn/ssenariy ----------------
PLATFORM_RULES = {
    "telegram": "Telegram: qisqa, aniq; media bilan 1024 belgigacha; 0-3 hashtag; oxirida aniq harakatga chaqiriq.",
    "instagram": "Instagram: birinchi 125 belgida kuchli hook; jami 2200 gacha; 5-10 hashtag; so'nggi qatorda CTA.",
    "youtube": "YouTube: birinchi qator = sarlavha (<=100 belgi, kalit so'z bilan); keyin tavsif (<=5000), vaqt belgilari va CTA.",
}


def smart_caption(business, platform: str, media_type: str, topic: str, current: str = "", user=None, router=None) -> dict:
    from apps.content.insights import insights_brief
    prompt = (f"Platforma: {platform}. Post turi: {media_type}. {PLATFORM_RULES.get(platform, '')}\n"
              f"Mavzu/maqsad: {topic or '(biznes uchun mos mavzu tanla)'}\n"
              f"Mavjud qoralama (bo'lsa yaxshila): {current[:1500]}\n"
              f"Shu biznesning o'z statistikasi (shundan o'rgan, nusxa ko'chirma):\n{insights_brief(business, platform)}\n"
              'JSON: {"variants":["taklif 1","taklif 2","taklif 3"],"hashtags":[],"why":"nega shunday (1 jumla)"}' + SUGGEST_ONLY)
    res, _ = generate(TaskType.LONG_UZ, prompt, business=business, kind="caption", user=user, schema=J, router=router)
    return res.data or {}


def _s(v) -> str:
    return str(v).strip() if v not in (None, "", [], {}) else ""


def script_text(body: dict) -> str:
    """Rejissyor ssenariysini odam o'qiydigan matnga aylantiradi (formaga/sahifaga)."""
    L: list[str] = []
    add = lambda *x: L.append(" ".join(str(i) for i in x if i))
    add("🎬", _s(body.get("title")))
    if body.get("concept"):
        add("G'OYA:", body["concept"])
    hv = body.get("hook_variants") or []
    if hv:
        add("HOOK (birinchi 3 soniya):", " | ".join(map(str, hv)))
    add("Davomiyligi:", f"{body['duration_sec']} soniya" if body.get("duration_sec") else "", "· Joy:", _s(body.get("location")))
    cast = body.get("cast") or []
    if cast:
        L.append("\nAKTYORLAR:")
        for c in cast:
            if isinstance(c, dict):
                L.append(f"  • {_s(c.get('role'))} — {_s(c.get('look'))} {_s(c.get('note'))}".rstrip())
    if body.get("equipment"):
        L.append("\nJIHOZ: " + "; ".join(map(str, body["equipment"])))
    au = body.get("audio") or {}
    if au:
        L.append("\nAUDIO:")
        if au.get("voice_style"):
            L.append("  • Ovoz: " + str(au["voice_style"]))
        if au.get("music_mood"):
            L.append("  • Musiqa: " + str(au["music_mood"]))
        for t in au.get("trending_audios") or []:
            if isinstance(t, dict):
                L.append(f"  ♫ {_s(t.get('name'))} — {_s(t.get('why'))} ({_s(t.get('where'))})")
        if au.get("trending_audios"):
            L.append("  (Trend nomlari taxminiy: Instagram → Reels → Audio → «Trending» bo'limidan tekshiring; audioni montajda videoga qo'shing.)")
        if au.get("sfx"):
            L.append("  • Ovoz effektlari: " + ", ".join(map(str, au["sfx"])))
    for sc in body.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        cam, act = sc.get("camera") or {}, sc.get("actor") or {}
        if not isinstance(cam, dict):
            cam = {"position": cam}
        if not isinstance(act, dict):
            act = {"action": act}
        L.append(f"\n── SAHNA {_s(sc.get('n'))} [{_s(sc.get('t'))}] {_s(sc.get('shot_type'))} ──")
        if cam:
            L.append(f"  📷 Kamera joyi: {_s(cam.get('position'))}")
            L.append(f"     Burchak: {_s(cam.get('angle'))}; harakat: {_s(cam.get('movement'))}; {_s(cam.get('orientation'))}")
        if act:
            L.append(f"  🎭 Aktyor: {_s(act.get('action'))}")
            if act.get("emotion"):
                L.append(f"     Ifoda: {act['emotion']}")
            if act.get("line"):
                L.append(f"     Gapiradi: «{act['line']}»")
        if sc.get("voiceover"):
            L.append(f"  🎙 Ovoz: {sc['voiceover']}")
        if sc.get("on_screen_text"):
            L.append(f"  🔤 Ekranda: {sc['on_screen_text']}")
        if sc.get("audio_cue"):
            L.append(f"  ♪ Audio: {sc['audio_cue']}")
        if sc.get("transition"):
            L.append(f"  ➜ O'tish: {sc['transition']}")
    if body.get("cta"):
        L.append("\nCTA: " + str(body["cta"]))
    if body.get("props"):
        L.append("REKVIZIT: " + ", ".join(map(str, body["props"])))
    if body.get("editing_notes"):
        L.append("\nMONTAJ:")
        L += [f"  • {n}" for n in body["editing_notes"]]
    pub = body.get("publishing") or {}
    if isinstance(pub, dict) and pub:
        L.append(f"\nNASHR: vaqt {_s(pub.get('best_time'))}; hashtag: {' '.join(map(str, pub.get('hashtags') or []))}")
    if body.get("checklist"):
        L.append("\nSURATGA OLISHDAN OLDIN:")
        L += [f"  ☐ {n}" for n in body["checklist"]]
    if body.get("notes"):
        L.append("\nIzoh: " + str(body["notes"]))
    return "\n".join(l for l in L if l is not None).strip()


def smart_youtube(business, media_type: str, topic: str, text: str, user=None, router=None) -> dict:
    from apps.content.insights import insights_brief
    prompt = ("YouTube uchun SEO sarlavha va teglarni tahlilga tayanib yoz. Sarlavha <=100 belgi, birinchi 40 belgida kalit so'z, "
              "clickbait emas, o'zbek tilida. Teglar 8-15 ta (kalit so'zlar, hashtagsiz). "
              'JSON: {"title":"","tags":["",""],"privacy":"public","why":"1 jumla"}\n'
              f"Format: {'Shorts' if media_type == 'short' else 'video'}. Mavzu: {topic or '(matndan ol)'}\n"
              f"Post matni: {(text or '')[:1500]}\nBiznes statistikasi:\n{insights_brief(business, 'youtube')}")
    res, _ = generate(TaskType.LONG_UZ, prompt, business=business, kind="yt_meta", user=user, schema=J, router=router)
    return res.data or {}


def smart_script(business, platform: str, media_type: str, brief: str, user=None, router=None):
    from apps.content.insights import insights_brief
    fmt = "long" if (platform == "youtube" and media_type == "video") else "reel"
    ctx = (f"\nPlatforma: {platform}. Statistikadan xulosa (shunga mos yoz):\n{insights_brief(business, platform)}\n"
           "Eng yaxshi postlarning uslubi/hooki ruhini saqla, lekin so'zma-so'z ko'chirma.")
    sc = generate_script(business, (brief or "Biznes uchun foydali qisqa video") + ctx, fmt, variants=2, user=user, router=router)
    return sc, script_text(sc.body or {})


# ---------------- Raqobatchilar xulosasi ----------------
def _competitor_facts(business) -> list[dict]:
    from datetime import timedelta
    from django.utils import timezone
    from apps.connections.models import Competitor
    from apps.metrics.models import CompetitorPost
    out = []
    since = timezone.now() - timedelta(days=30)
    for c in Competitor.objects.filter(business=business, active=True):
        posts = list(CompetitorPost.objects.filter(competitor=c, published_at__gte=since).order_by("-views")[:40])
        last = c.metrics.order_by("-taken_at").first()
        first = c.metrics.order_by("taken_at").first()
        tags = {}
        for p in posts:
            for h in re.findall(r"#\w+", p.text or ""):
                tags[h.lower()] = tags.get(h.lower(), 0) + 1
        types = {}
        for p in posts:
            types[p.media_type or "post"] = types.get(p.media_type or "post", 0) + 1
        out.append({
            "nomi": c.name or c.handle, "tarmoq": c.platform,
            "obunachi": last.followers if last else None,
            "obunachi_osishi": (last.followers - first.followers) if last and first and last.followers is not None and first.followers is not None else None,
            "30_kunda_post": len(posts), "haftasiga": round(len(posts) / 4.3, 1),
            "turlari": types, "top_hashtag": sorted(tags, key=tags.get, reverse=True)[:5],
            "eng_yaxshi_postlar": [{"matn": (p.text or "")[:140], "korish": p.views, "layk": p.likes} for p in posts[:3]],
        })
    return out


def competitor_summary(business, user=None, router=None):
    facts = _competitor_facts(business)
    if not facts:
        raise ValueError("Avval kamida bitta raqobatchi qo'shing.")
    from apps.metrics.analytics import post_frequency
    mine = post_frequency(business)
    prompt = ("Sen SMM strategsan. Raqobatchilar ma'lumotini SOLISHTIRIB, biznes egasi tushunadigan oddiy o'zbek tilida xulosa yoz. "
              "Faqat berilgan raqamlarni ishlat, o'ylab topma. Raqobatchi matnlarini nusxalama, faqat g'oya ol. "
              'JSON: {"summary":"3-4 gap umumiy xulosa","competitors":[{"name":"","strength":"","weakness":""}],'
              '"gaps":["raqobatchilar qilmayotgan, biz ishlatsak bo\'ladigan yo\'nalish"],"actions":["bu hafta qilinadigan aniq ish"],"watch":["e\'tibor berish kerak"]}\n'
              f"Bizning tezlik: {mine}\nRaqobatchilar: {json.dumps(facts, ensure_ascii=False, default=str)[:5000]}")
    res, gen = generate(TaskType.LONG_UZ, prompt, business=business, kind="competitor_summary", user=user, schema=J, router=router)
    if not res.data:
        gen.data = {"summary": res.text or "Xulosa olinmadi."}
        gen.save(update_fields=["data"])
    return gen


# ---------------- Dizayner uchun mavzular ----------------
def design_topics(business, platform: str = "", count: int = 8, user=None, router=None):
    from apps.metrics.analytics import best_times, by_type, hashtag_stats, top_posts
    tops = [{"matn": r.post.text[:120], "tur": r.post.media_type, "er": r.er} for r in top_posts(business, 5)]
    worst = [{"matn": r.post.text[:100], "tur": r.post.media_type, "er": r.er} for r in top_posts(business, 3, worst=True)]
    comp = [{"nomi": f["nomi"], "top": [p["matn"] for p in f["eng_yaxshi_postlar"][:2]]} for f in _competitor_facts(business)]
    ctx = {"eng_yaxshi": tops, "eng_yomon": worst, "turlar": by_type(business), "vaqtlar": best_times(business),
           "hashtag": hashtag_stats(business), "raqobatchi_g_oyalari": comp}
    plat = platform if platform in ("telegram", "instagram", "youtube") else "telegram, instagram, youtube"
    prompt = (f"Dizayner/video montajchi uchun {count} ta ishlab chiqarish topshirig'i (mavzu) tayyorla. Platforma: {plat}. "
              "Tahlilga tayanib: nima yaxshi ishlagan bo'lsa shuni davom ettir, yomon ishlaganini takrorlama. Raqobatchini nusxalama. "
              'JSON: {"summary":"nima uchun aynan shu mavzular (2 gap)","topics":[{"platform":"telegram|instagram|youtube","format":"image|carousel|reel|short|video|story",'
              '"topic":"","why":"tahlildan sabab","visual_brief":"dizayner uchun aniq vazifa: kadr, ranglar, matn","script":"video bo\'lsa qisqa ssenariy","hook":"","cta":"","best_time":"HH:MM","duration_sec":0}]}\n'
              f"Tahlil: {json.dumps(ctx, ensure_ascii=False, default=str)[:4500]}")
    res, gen = generate(TaskType.LONG_UZ, prompt, business=business, kind="design_topics", user=user, schema=J, router=router)
    return gen


def load_topics_to_calendar(gen, user=None) -> int:
    """Mavzularni qoralama sifatida kalendarga (keyingi kunlarga) qo'yadi — dizayner media yuklaydi."""
    from datetime import timedelta
    from django.utils import timezone
    from apps.connections.models import SocialAccount
    from apps.content.models import ContentItem, ContentTarget
    biz = gen.business
    n, day = 0, timezone.localdate(timezone.now()) + timedelta(days=1)
    for t in (gen.data or {}).get("topics", []):
        if not isinstance(t, dict):
            continue
        fmt = t.get("format") if t.get("format") in ("image", "carousel", "reel", "short", "video", "story") else "image"
        try:
            hh, mm = (int(x) for x in str(t.get("best_time") or "19:00").split(":")[:2])
        except ValueError:
            hh, mm = 19, 0
        when = datetime.combine(day, time(hh % 24, mm % 60), tzinfo=tz())
        item = ContentItem.objects.create(
            business=biz, title=(t.get("topic") or "Mavzu")[:200], text="", media_type=fmt, status="draft", scheduled_at=None,
            hook_idea=str(t.get("hook", ""))[:300], cta=str(t.get("cta", ""))[:200], created_by=user, ai_draft=True,
            notes=f"DIZAYNER UCHUN: {t.get('visual_brief', '')}\n\nSSENARIY: {t.get('script', '')}\n\nTavsiya vaqt: {when:%d.%m %H:%M}\nSabab: {t.get('why', '')}")
        acc = SocialAccount.objects.filter(business=biz, platform=t.get("platform"), archived_at__isnull=True).first()
        if acc:
            ContentTarget.objects.create(item=item, account=acc)
        n += 1
        day += timedelta(days=1)
    return n
