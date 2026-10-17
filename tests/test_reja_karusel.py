"""Kontent reja (har tarmoq alohida), karusel ssenariy (dinamik slayd/qismlar), video ssenariy, 14 tur andozasi."""
import json
from datetime import date

import pytest
from django.test import Client

from apps.ai_router.providers import FakeAIProvider
from apps.ai_router.router import AIRouter

pytestmark = pytest.mark.django_db


def _router(*items):
    return AIRouter(providers={n: FakeAIProvider(n, list(items) if n == "openai" else []) for n in ("openai", "claude")}, use_fakes=True)


def test_all_14_types_have_playbook():
    from apps.businesses.models import BusinessTemplate
    from apps.businesses.playbooks import PLAYBOOKS
    keys = list(BusinessTemplate.objects.values_list("key", flat=True))
    assert len(keys) == 14
    for k in keys:
        pb = PLAYBOOKS[k]
        assert sum(p["share"] for p in pb["pillars"]) == 100, k
        assert len(pb["ideas"]) >= 6 and len(pb["angles"]) >= 2 and pb["cta"], k
        assert {i["pillar"] for i in pb["ideas"]} <= {p["key"] for p in pb["pillars"]}, k
        assert all(i["format"] in ("post", "carousel", "reel", "video", "story") for i in pb["ideas"]), k


def test_slots_per_platform_are_separate_and_valid(biz):
    from apps.studio import planner as pl
    m = date(2027, 3, 1)
    plans = {}
    for plat in ("telegram", "instagram", "youtube"):
        plans[plat] = pl.create_plan(biz, plat, m)
    assert len({p.pk for p in plans.values()}) == 3
    for plat, p in plans.items():
        assert p.entries and p.platform == plat
        assert all(e["format"] in pl.PLATFORM_FORMATS[plat] for e in p.entries)
        assert all(date.fromisoformat(e["date"]).month == 3 for e in p.entries)
    assert len(plans["telegram"].entries) > len(plans["youtube"].entries)
    # Navro'z va 8-mart bayrami biror bo'lakka biriktirilgan
    occ = " ".join(e["occasion"] for e in plans["telegram"].entries)
    assert "Navro'z" in occ
    # sotuv ustuni ketma-ket kelmaydi
    pil = [e["pillar"] for e in plans["telegram"].entries]
    assert all(not (a == b == "sotuv") for a, b in zip(pil, pil[1:]))


def test_ai_fill_uzbek_only_and_dedupe(biz):
    from apps.studio import planner as pl
    p = pl.create_plan(biz, "instagram", date(2027, 3, 1))
    ok = {"summary": "Mart oyi strategiyasi.", "goal": "Yangi guruhga yozilish", "tone": "do'stona", "key_messages": ["Natija", "Ishonch"],
          "entries": [{"i": 0, "topic": "Ingliz tilini 3 oyda o'rganish yo'li", "hook": "Nega ko'pchilik tilni tashlab ketadi?", "cta": "Telegramga yozing", "goal": "lead", "brief": "Doskada yozuv"},
                      {"i": 1, "topic": "Как выучить английский быстро", "hook": "Привет", "cta": "Пишите", "goal": "x", "brief": ""}]}
    n = pl.fill_with_ai(p, router=_router(json.dumps(ok)))
    p.refresh_from_db()
    assert n == 1 and p.entries[0]["source"] == "ai" and p.entries[1]["source"] == "andoza"  # kirill qator rad etildi
    assert p.strategy["ai_state"] == "ok" and p.strategy["goal"] and p.summary == "Mart oyi strategiyasi."


def test_ai_failure_keeps_template_plan(biz):
    from apps.studio import planner as pl
    p = pl.create_plan(biz, "telegram", date(2027, 3, 1))
    broken = AIRouter(providers={n: FakeAIProvider(n, [RuntimeError("x")] * 6) for n in ("openai", "claude")}, use_fakes=True)
    assert pl.fill_with_ai(p, router=broken) == 0
    p.refresh_from_db()
    assert p.strategy["ai_state"] == "fallback" and p.entries and all(e["topic"] for e in p.entries)


def test_load_to_calendar_no_duplicates(biz, acc_tg, admin):
    from apps.content.models import ContentItem
    from apps.studio import planner as pl
    p = pl.create_plan(biz, "telegram", date(2027, 3, 1), admin)
    n = pl.load_to_calendar(p, admin)
    assert n == len(p.entries) and p.loaded_to_calendar
    assert pl.load_to_calendar(p, admin) == 0
    assert ContentItem.objects.filter(plan=p).count() == n
    assert ContentItem.objects.filter(plan=p).first().targets.count() == 1


def test_split_counts():
    from apps.studio.carousel import split_counts
    assert split_counts(7) == [7] and split_counts(10) == [10]
    assert split_counts(16) == [8, 8] and split_counts(11) == [6, 5]
    assert split_counts(21) == [7, 7, 7] and sum(split_counts(30)) == 30 and max(split_counts(30)) <= 10


def _slides(n):
    return [{"role": "hook" if i == 0 else ("cta" if i == n - 1 else "yechim"), "title": f"Sarlavha {i + 1} bu juda uzun sarlavha bo'lib ketdi",
             "text": "So'z " * 40, "visual": "Fon va katta yozuv"} for i in range(n)]


def test_carousel_dynamic_slides_and_parts(biz, admin):
    from apps.studio import carousel as cs
    r = _router(json.dumps({"title": "Aziza ingliz tilini qanday o'rgandi", "logline": "Mijoz hikoyasi", "hero": "Aziza", "slides": _slides(16),
                            "caption": "Hikoya", "hashtags": ["ingliztili", "#kurs"], "style": {"palette": "ko'k, oq"}}))
    c = cs.generate_carousel(biz, "Aziza hikoyasi", size="long", user=admin, router=r)
    assert len(c.slides) == 16 and [len(p["slides"]) for p in c.parts] == [8, 8]
    assert all(len(s["title"].split()) <= 6 and len(s["text"].split()) <= 18 for s in c.slides)
    assert c.parts[0]["title"].endswith("1-qism") and "Davomi" in c.parts[0]["overlay_last"] and c.parts[1]["overlay_last"] == ""
    assert "1/2-qism" in c.parts[0]["caption"] and "#ingliztili" in c.parts[0]["hashtags"]
    assert "1-SLAYD" in cs.part_text(c, c.parts[0])
    short = cs.generate_carousel(biz, "Qisqa", router=_router(json.dumps({"title": "T", "slides": _slides(6), "caption": "c"})))
    assert len(short.parts) == 1 and short.parts[0]["title"] == short.title


def test_carousel_fallback_and_cyrillic(biz):
    from apps.studio import carousel as cs
    bad = _slides(6)
    bad[2]["text"] = "Привет мир"
    c = cs.generate_carousel(biz, "Mavzu", router=_router(json.dumps({"title": "x", "slides": bad}), json.dumps({"title": "x", "slides": bad})))
    assert c.story["source"] == "andoza" and len(c.slides) >= 3   # kirill -> andoza skelet
    broken = AIRouter(providers={n: FakeAIProvider(n, [RuntimeError("x")] * 6) for n in ("openai", "claude")}, use_fakes=True)
    assert cs.generate_carousel(biz, "Mavzu", router=broken).slides


def test_carousel_load_part_to_calendar(biz, admin):
    from apps.content.models import ContentItem
    from apps.studio import carousel as cs
    c = cs.generate_carousel(biz, "X", router=_router(json.dumps({"title": "T", "slides": _slides(14), "caption": "c"})))
    assert len(c.parts) == 2
    pk = cs.load_part_to_calendar(c, 1, admin)
    it = ContentItem.objects.get(pk=pk)
    assert it.media_type == "carousel" and it.status == "draft" and "1-SLAYD" in it.brief
    assert cs.load_part_to_calendar(c, 1, admin) is None


def test_video_script_prompt_is_detailed(biz, admin):
    from apps.studio import services as st
    scenes = [{"n": 1, "t": "0-3s", "shot_type": "close-up", "camera": {"position": "old tomonda"}, "actor": {"action": "kuladi", "line": "Salom"}}]
    body = {"title": "Kurs", "plain_summary": ["1) Salomlashing", "2) Ko'rsating"], "scenes": scenes, "why_it_works": "Qisqa", "cta": "Yoziling"}
    s = st.generate_script(biz, "kurs", "reel", user=admin, router=_router(json.dumps(body)))
    txt = st.script_text(s.body)
    assert "QISQACHA REJA" in txt and "Sahnalar soni" in txt and "NEGA ISHLAYDI" in txt and "SAHNA 1" in txt
    from apps.ai_router.models import AIGeneration
    pr = AIGeneration.objects.filter(kind="script").first().prompt
    assert "Test Markaz" in pr and "rejissyorsiz" in pr


def test_web_pages(biz, admin):
    c = Client()
    c.force_login(admin)
    c.post("/biznes-tanlash/", {"business": biz.pk})
    for u in ("/reja/", "/karusel/", "/studiya/?tab=reja"):
        assert c.get(u).status_code == 200, u
    r = c.post("/reja/yaratish/", {"month": f"{date.today().year + 1}-03", "platforms": ["telegram", "instagram"], "ppw": ""})
    assert r.status_code == 302
    from apps.studio.models import ContentPlan
    assert ContentPlan.objects.filter(business=biz).count() == 2
    p = ContentPlan.objects.filter(platform="instagram").first()
    page = c.get(f"/reja/{p.pk}/")
    assert page.status_code == 200 and "Hook" in page.content.decode()
    r = c.post(f"/reja/{p.pk}/amal/", {"act": "approve", "n": 0})
    p.refresh_from_db()
    assert p.status == "approved"
    r = c.post("/karusel/yaratish/", {"topic": "Test mavzu", "size": "auto", "platform": "instagram"})
    assert r.status_code == 302
    from apps.studio.models import Carousel
    cr = Carousel.objects.get()
    assert c.get(f"/karusel/{cr.pk}/").status_code == 200
    assert c.get(f"/studiya/reja/{p.pk}/").status_code == 302


def _form(p):
    d = {"n": len(p.entries)}
    for i, e in enumerate(p.entries):
        for k in ("date", "time", "format", "topic", "hook", "cta", "goal", "brief", "pillar", "pillar_name", "occasion", "source"):
            d[f"{k}_{i}"] = e.get(k, "")
    return d


def test_plan_edit_actions(biz, acc_tg, admin):
    from apps.content.models import ContentItem
    from apps.studio import planner as pl
    c = Client(); c.force_login(admin); c.post("/biznes-tanlash/", {"business": biz.pk})
    p = pl.create_plan(biz, "telegram", date(date.today().year + 1, 3, 1), admin)
    n0 = len(p.entries)
    d = _form(p); d["act"] = "save"; d["topic_0"] = "Mening mavzum"; d["format_0"] = "NOTAVALID"
    assert c.post(f"/reja/{p.pk}/amal/", d).status_code == 302
    p.refresh_from_db()
    assert any(e["topic"] == "Mening mavzum" for e in p.entries) and all(e["format"] in pl.PLATFORM_FORMATS["telegram"] for e in p.entries)
    d = _form(p); d["act"] = "del:0"
    c.post(f"/reja/{p.pk}/amal/", d); p.refresh_from_db()
    assert len(p.entries) == n0 - 1
    d = _form(p); d["act"] = "add"
    c.post(f"/reja/{p.pk}/amal/", d); p.refresh_from_db()
    assert len(p.entries) == n0
    d = _form(p); d["act"] = "regen:1"
    assert c.post(f"/reja/{p.pk}/amal/", d).status_code == 302
    ci = next(i for i, e in enumerate(p.entries) if e["format"] == "carousel")
    d = _form(p); d["act"] = f"karusel:{ci}"
    r = c.post(f"/reja/{p.pk}/amal/", d)
    assert r.status_code == 302 and r["Location"].startswith("/karusel/")
    d = _form(p); d["act"] = "load"
    c.post(f"/reja/{p.pk}/amal/", d)
    assert ContentItem.objects.filter(plan=p).count() == n0
    assert c.post(f"/reja/{p.pk}/amal/", {"act": "delete_plan"}).status_code == 302


def test_carousel_edit_actions(biz, acc_tg, admin):
    from apps.studio import carousel as cs
    from apps.studio.models import Carousel
    c = Client(); c.force_login(admin); c.post("/biznes-tanlash/", {"business": biz.pk})
    car = cs.generate_carousel(biz, "X", router=_router(json.dumps({"title": "T", "slides": _slides(10), "caption": "c"})))
    assert len(car.parts) == 1
    base = {"total": 10}
    assert c.post(f"/karusel/{car.pk}/amal/", {**base, "act": "addafter:3"}).status_code == 302
    car.refresh_from_db(); assert len(car.slides) == 11 and [len(p["slides"]) for p in car.parts] == [6, 5]
    c.post(f"/karusel/{car.pk}/amal/", {"act": "load:2"})
    car.refresh_from_db(); assert car.parts[1]["item_id"]
    c.post(f"/karusel/{car.pk}/amal/", {"act": "del:1"})
    car.refresh_from_db(); assert len(car.slides) == 10 and len(car.parts) == 1
    c.post(f"/karusel/{car.pk}/amal/", {"act": "regen:2", "instruction": "qisqaroq"})
    c.post(f"/karusel/{car.pk}/amal/", {"act": "ready"})
    car.refresh_from_db(); assert car.status == "ready"
    c.post(f"/karusel/{car.pk}/amal/", {"act": "delete"})
    assert not Carousel.objects.filter(pk=car.pk).exists()


def test_carousel_analysis_mode(biz, admin):
    from apps.studio import carousel as cs
    from apps.ai_router.models import AIGeneration
    d = {"title": "Aziza hikoyasi", "slides": _slides(7), "caption": "c",
         "analysis": {"summary": "Markaz noldan o'rgatadi.", "audience_insight": "Mijoz tilni o'zi o'rganib qiynaladi.", "chosen_topic": "Noldan boshlash", "why": "Asosiy og'riq shu."}}
    c = cs.generate_carousel(biz, "", mode="analysis", router=_router(json.dumps(d)))
    assert c.story["mode"] == "analysis" and c.story["analysis"]["chosen_topic"] == "Noldan boshlash" and c.topic == "Noldan boshlash"
    assert "TAHLIL REJIMI" in AIGeneration.objects.filter(kind="carousel").first().prompt


def test_analysis_mode_web_and_logo(biz, admin, tmp_path, settings):
    from django.core.files.uploadedfile import SimpleUploadedFile
    settings.MEDIA_ROOT = str(tmp_path)
    c = Client(); c.force_login(admin); c.post("/biznes-tanlash/", {"business": biz.pk})
    assert c.post("/karusel/yaratish/", {"mode": "analysis", "topic": "", "size": "auto", "platform": "instagram"}).status_code == 302
    from apps.studio.models import Carousel
    assert Carousel.objects.filter(business=biz).count() == 1
    assert c.post("/karusel/yaratish/", {"mode": "topic", "topic": ""}).status_code == 302
    assert Carousel.objects.filter(business=biz).count() == 1
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082")
    biz.logo.save("l.png", SimpleUploadedFile("l.png", png), save=True)
    r = c.get(f"/bizneslar/{biz.pk}/logo/")
    assert r.status_code == 200 and r["Content-Type"] == "image/png"
    assert f"/bizneslar/{biz.pk}/logo/" in c.get(f"/bizneslar/{biz.pk}/").content.decode()


def test_parse_buttons_rows():
    from apps.web.forms import parse_buttons
    raw = "A | https://a.uz\nB | https://b.uz\nC | https://c.uz\nD | https://d.uz || E | https://e.uz"
    assert [len(r) for r in parse_buttons(raw, 2)] == [2, 1, 2]
    assert [len(r) for r in parse_buttons(raw, 3)] == [3, 2]
    assert [len(r) for r in parse_buttons("A | https://a.uz\nB | https://b.uz", 1)] == [1, 1]
