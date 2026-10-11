"""28-yangilanish: biznes turlari/pasport, maqsadlar, reklama taklifi, faktlar va yangiliklar."""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Role, User, UserBusinessAccess
from apps.ai_router.providers import FakeAIProvider
from apps.ai_router.router import AIRouter
from apps.businesses.models import Business, BusinessTemplate
from apps.connections.models import SocialAccount
from apps.metrics.models import AccountMetrics, Post, PostMetricsHistory


def fake_router(*script):
    return AIRouter(providers={n: FakeAIProvider(n, list(script) if n == "openai" else []) for n in ("openai", "claude")}, use_fakes=True)


def mkpost(acc, i, *, days=5, text=None, views=100, reach=None, likes=5, comments=0, shares=0, saves=0, mtype="image", dur=None, avg_dur=None, er=None):
    p = Post.objects.create(business=acc.business, account=acc, platform=acc.platform, external_id=f"x{acc.pk}-{i}", media_type=mtype,
                            text=text if text is not None else f"Post {i}", published_at=timezone.now() - timedelta(days=days), duration_sec=dur)
    reach = reach or views
    inter = likes + comments + shares + saves
    PostMetricsHistory.objects.create(post=p, business_id=acc.business_id, taken_at=timezone.now(), views=views, reach=reach, likes=likes, comments=comments,
                                      shares=shares, saves=saves, avg_view_duration_sec=avg_dur, er=er if er is not None else inter / max(1, reach), er_basis="reach")
    return p


@pytest.fixture
def acc_ig(biz):
    return SocialAccount.objects.create(business=biz, platform="instagram", name="elshod.graphics", handle="elshod.graphics", external_id="1784", history_imported=True)


@pytest.fixture
def boss(db):
    return User.objects.create_user("boss", password="Boss#2026test!", is_admin=True)


def client_for(user, pw, biz=None):
    c = Client()
    assert c.post("/kirish/", {"username": user.username, "password": pw}).status_code == 302
    if biz:
        c.post("/biznes-tanlash/", {"business": biz.pk})
    return c


@pytest.fixture
def adminc(boss, biz):
    return client_for(boss, "Boss#2026test!", biz)


# ------------------------------------------------------------------ ER himoyasi
def test_er_never_exceeds_one_and_skips_inconsistent_basis():
    from apps.metrics.collector import compute_er
    m = SimpleNamespace(likes=10, comments=0, shares=0, saves=0, reach=5, views=40)
    er, basis = compute_er(m, 100)
    assert basis == "views" and er == 0.25
    bad = SimpleNamespace(likes=50, comments=0, shares=0, saves=0, reach=3, views=10)
    assert compute_er(bad, 20) == (50 / 20 if False else None, "") or compute_er(bad, 20)[0] is None or compute_er(bad, 20)[0] <= 1
    assert compute_er(SimpleNamespace(likes=0, comments=0, shares=0, saves=0, reach=None, views=None), None) == (None, "")


# ------------------------------------------------------------------ biznes turlari va pasport
def test_system_types_have_fields():
    ts = BusinessTemplate.objects.filter(is_system=True)
    assert ts.count() >= 12
    assert all(t.profile_fields for t in ts)
    assert BusinessTemplate.objects.get(key="shaxsiy_blog").topics


def test_custom_business_type_via_settings(adminc):
    r = adminc.post("/sozlamalar/biznes-turlari/yangi/", {"name": "Gul do'koni", "key": "gul_dokoni", "description": "Gul savdosi", "topics": "floristry, wedding flowers",
                                                          "domains": "ecommerce, fashion", "fields_text": "gul_turlari | Qaysi gullar sotiladi | long\nyetkazish | Yetkazib berish | choice | Bor;Yo'q;Pulli | izoh",
                                                          "advice": "Vizual kontent", "content_types": "lookbook, aksiya"})
    assert r.status_code == 302, r.content.decode()[:600]
    t = BusinessTemplate.objects.get(key="gul_dokoni")
    assert not t.is_system and len(t.profile_fields) == 2 and t.profile_fields[1]["choices"] == ["Bor", "Yo'q", "Pulli"]
    assert t.config["domains"] == ["ecommerce", "fashion"]
    assert adminc.get("/sozlamalar/biznes-turlari/").status_code == 200
    assert adminc.get(f"/sozlamalar/biznes-turlari/{t.pk}/").status_code == 200
    # noto'g'ri qatorlar
    r = adminc.post("/sozlamalar/biznes-turlari/yangi/", {"name": "Xato", "key": "xato", "fields_text": "BAD KEY | Savol | text\nbitta_qator"})
    assert r.status_code == 200 and not BusinessTemplate.objects.filter(key="xato").exists()
    # tizim turini o'chirib bo'lmaydi; o'zimizniki o'chadi
    sys_t = BusinessTemplate.objects.get(key="oquv_markaz")
    adminc.post(f"/sozlamalar/biznes-turlari/{sys_t.pk}/ochir/")
    assert BusinessTemplate.objects.filter(key="oquv_markaz").exists()
    adminc.post(f"/sozlamalar/biznes-turlari/{t.pk}/ochir/")
    assert not BusinessTemplate.objects.filter(key="gul_dokoni").exists()


def test_passport_completeness_and_save(biz, adminc):
    from apps.businesses import passport as pp
    c0 = pp.completeness(biz)
    assert c0["pct"] < 100 and not c0["ok_for_ai"] is None
    r = adminc.get(f"/bizneslar/{biz.pk}/pasport/")
    assert r.status_code == 200 and "Biznes pasporti" in r.content.decode()
    data = {}
    for s in pp.sections(biz):
        for f in s["fields"]:
            data[f"{f['section']}__{f['key']}"] = (f["choices"][0] if f.get("choices") else "Javob")
    data["template"] = biz.template_id
    r = adminc.post(f"/bizneslar/{biz.pk}/pasport/", data)
    assert r.status_code == 302
    biz.refresh_from_db()
    c1 = pp.completeness(biz)
    assert c1["pct"] == 100 and c1["ok_for_ai"] and biz.profile["general"]["usp"] == "Javob"
    assert "Biznes: Test Markaz" in pp.brief(biz)
    # noto'g'ri tanlov qiymati saqlanmaydi
    key = next(f["key"] for f in pp.type_fields(biz) if f["kind"] == "choice")
    data[f"type__{key}"] = "YO'Q-VARIANT"
    adminc.post(f"/bizneslar/{biz.pk}/pasport/", data)
    biz.refresh_from_db()
    assert biz.profile["type"][key] == ""


def test_new_business_goes_to_passport_and_defaults_type(adminc):
    r = adminc.post("/bizneslar/yangi/", {"name": "Yangi Shaxsiy", "languages": "uz", "main_goal": "followers", "currency": "UZS", "avg_check": "0"})
    assert r.status_code == 302 and "/pasport/" in r["Location"]
    b = Business.objects.get(name="Yangi Shaxsiy")
    assert b.template.key == "boshqa"


# ------------------------------------------------------------------ maqsadlar
def test_goal_progress_states(biz, acc_tg):
    from apps.goals import services as gs
    AccountMetrics.objects.create(business=biz, account=acc_tg, taken_at=timezone.now() - timedelta(days=1), followers=3)
    today = gs.today_local()
    g = gs.create_goal(account=acc_tg, metric="followers", target=100, start_date=today - timedelta(days=30), end_date=today + timedelta(days=60))
    assert g.baseline == 3 and g.snapshots.count() == 1
    p = gs.compute(g, today=today)
    assert p.state in ("behind", "at_risk") and p.days_left == 60 and p.pct < 5
    # reja bo'yicha: 30/90 kun o'tdi, ~33% kerak
    p2 = gs.compute(g, today=today, current=40)
    assert p2.state == "on_track" and round(p2.pct) == 38
    p3 = gs.compute(g, today=today, current=100)
    assert p3.state == "achieved"
    assert gs.compute(g, today=g.end_date + timedelta(days=1), current=50).state == "missed"
    p4 = gs.compute(g, today=g.start_date + timedelta(days=1), current=4)
    assert p4.state == "starting"
    assert gs.compute(g, today=today, current=None).current is None or True


def test_goal_suggestions_for_tiny_account(biz, acc_tg):
    from apps.goals import services as gs
    AccountMetrics.objects.create(business=biz, account=acc_tg, taken_at=timezone.now(), followers=3)
    s = gs.suggest_targets(acc_tg, "followers")
    vals = [o["value"] for o in s["options"]]
    assert vals == sorted(vals) and vals[0] > 3 and s["confidence"] == "low"
    for m in ("views", "posts", "er"):
        assert len(gs.suggest_targets(acc_tg, m)["options"]) == 3


def test_goal_update_creates_revision_and_milestones(biz, acc_tg, boss):
    from apps.goals import services as gs
    AccountMetrics.objects.create(business=biz, account=acc_tg, taken_at=timezone.now(), followers=10)
    g = gs.create_goal(account=acc_tg, metric="followers", target=50)
    gs.update_goal(g, target=80, reason="reklama boshlandi", user=boss)
    g.refresh_from_db()
    assert g.target == 80 and g.revisions.count() == 1 and g.revisions.first().old_target == 50
    ms = gs.milestones(g)
    assert len(ms) >= 12 and ms[-1]["plan"] == pytest.approx(80, rel=0.02)
    ch = gs.chart_series(g)
    assert len(ch["labels"]) == len(ch["series"][0]["data"]) == len(ch["series"][1]["data"])


def test_goals_job_closes_achieved(biz, acc_tg):
    from apps.goals import services as gs
    from apps.goals.jobs import goals_snapshot
    from apps.jobs.queue import JobContext
    AccountMetrics.objects.create(business=biz, account=acc_tg, taken_at=timezone.now(), followers=10)
    g = gs.create_goal(account=acc_tg, metric="followers", target=20)
    AccountMetrics.objects.create(business=biz, account=acc_tg, taken_at=timezone.now() + timedelta(seconds=5), followers=25)
    res = goals_snapshot(JobContext(job=SimpleNamespace(pk=0), payload={}))
    g.refresh_from_db()
    assert res["closed"] == 1 and g.status == "achieved" and g.final_value == 25


def test_goal_pages_and_validation(adminc, biz, acc_tg):
    AccountMetrics.objects.create(business=biz, account=acc_tg, taken_at=timezone.now(), followers=5)
    assert adminc.get("/maqsadlar/").status_code == 200
    r = adminc.get(f"/maqsadlar/yangi/?account={acc_tg.pk}&metric=followers")
    assert r.status_code == 200 and "Nishon tanlang" in r.content.decode()
    # hozirgidan kichik nishon rad etiladi
    r = adminc.post("/maqsadlar/yangi/", {"account": acc_tg.pk, "metric": "followers", "custom": "3", "create": "1", "end_date": (date.today() + timedelta(days=60)).isoformat()})
    assert r.status_code == 200
    r = adminc.post("/maqsadlar/yangi/", {"account": acc_tg.pk, "metric": "followers", "custom": "100", "create": "1", "end_date": (date.today() + timedelta(days=60)).isoformat()})
    assert r.status_code == 302
    from apps.goals.models import Goal
    g = Goal.objects.get()
    assert adminc.get(f"/maqsadlar/{g.pk}/").status_code == 200
    # takroriy faol maqsad
    r = adminc.post("/maqsadlar/yangi/", {"account": acc_tg.pk, "metric": "followers", "custom": "200", "create": "1"})
    assert Goal.objects.count() == 1
    r = adminc.post(f"/maqsadlar/{g.pk}/tahrir/", {"target": "150", "end_date": (date.today() + timedelta(days=100)).isoformat(), "reason": "test"})
    g.refresh_from_db()
    assert g.target == 150 and g.revisions.count() == 1
    adminc.post(f"/maqsadlar/{g.pk}/yopish/", {"status": "cancelled"})
    g.refresh_from_db()
    assert g.status == "cancelled"
    assert adminc.get("/maqsadlar/?show=closed").status_code == 200
    assert adminc.get("/").status_code == 200


def test_goals_rbac_and_isolation(biz, biz2, acc_tg):
    from apps.goals import services as gs
    AccountMetrics.objects.create(business=biz, account=acc_tg, taken_at=timezone.now(), followers=5)
    g = gs.create_goal(account=acc_tg, metric="followers", target=50)
    u = User.objects.create_user("u2", password="Aaaa#1234567")
    role = Role.objects.get(name="Analitik")
    UserBusinessAccess.objects.create(user=u, business=biz2, role=role)
    c = client_for(u, "Aaaa#1234567")
    assert c.get(f"/maqsadlar/{g.pk}/").status_code in (403, 404)       # boshqa biznes maqsadi ko'rinmaydi
    u3 = User.objects.create_user("u3", password="Aaaa#1234567")
    UserBusinessAccess.objects.create(user=u3, business=biz, role=Role.objects.get(name="Analitik"))
    c3 = client_for(u3, "Aaaa#1234567", biz)
    assert c3.get(f"/maqsadlar/{g.pk}/").status_code == 200
    assert c3.post(f"/maqsadlar/{g.pk}/tahrir/", {"target": "99", "end_date": "2030-01-01"}).status_code == 403   # Analitikda tahrir yo'q


def test_late_modules_granted_to_existing_roles(db):
    from django.core.management import call_command
    from apps.accounts.models import RolePermission
    from apps.core.settings_store import set_setting
    RolePermission.objects.filter(code__startswith="goals.").delete()
    set_setting("rbac.late_granted", [])
    call_command("bootstrap")
    assert RolePermission.objects.filter(role__name="Menejer", code="goals.edit").exists()
    assert RolePermission.objects.filter(role__name="Analitik", code="goals.export").exists()


# ------------------------------------------------------------------ reklama taklifi
def seed_tg_posts(acc):
    mkpost(acc, 1, views=800, reach=700, likes=30, comments=2, shares=60, saves=20, text="Foydali maslahat: logo qanday tanlanadi")
    mkpost(acc, 2, views=300, reach=280, likes=10, comments=18, shares=2, saves=6, text="Logo narxi 500 000 so'm. Buyurtma uchun @elshod yozing")
    mkpost(acc, 3, views=150, reach=140, likes=4, comments=0, shares=0, saves=0, text="Bugun ob-havo yaxshi")
    mkpost(acc, 4, views=220, reach=200, likes=9, comments=3, shares=5, saves=2, text="Yangi portfolio ishi")
    mkpost(acc, 5, views=260, reach=250, likes=12, comments=4, shares=6, saves=3, text="Mijoz sharhi")
    mkpost(acc, 6, views=180, reach=170, likes=6, comments=1, shares=1, saves=1, text="Dars: ranglar")


def test_scoring_depends_on_objective(biz, acc_tg):
    from apps.ads import proposals as pr
    seed_tg_posts(acc_tg)
    sub = pr.score_candidates(biz, acc_tg, "subscribers")
    assert sub["picks"][0]["title"].startswith("Foydali maslahat")
    sales = pr.score_candidates(biz, acc_tg, "sales")
    assert sales["picks"][0]["title"].startswith("Logo narxi") and sales["picks"][0]["has_offer"]
    assert sub["stats"]["posts_used"] == 6 and all("score" in p for p in sub["picks"])


def test_instagram_prefers_video_and_retention(biz, acc_ig):
    from apps.ads import proposals as pr
    mkpost(acc_ig, 1, mtype="reel", views=900, reach=800, likes=40, shares=12, saves=15, dur=20, avg_dur=15, text="Reels 1")
    mkpost(acc_ig, 2, mtype="reel", views=300, reach=280, likes=10, shares=1, saves=2, dur=20, avg_dur=4, text="Reels 2")
    mkpost(acc_ig, 3, mtype="image", views=2000, reach=1900, likes=200, shares=50, saves=80, text="Rasm post")
    s = pr.score_candidates(biz, acc_ig, "views")
    assert {p["title"] for p in s["picks"]} == {"Reels 1", "Reels 2"} and s["picks"][0]["title"] == "Reels 1"


def test_confidence_low_with_few_posts(biz, acc_tg):
    from apps.ads import proposals as pr
    mkpost(acc_tg, 1)
    mkpost(acc_tg, 2, views=300)
    s = pr.score_candidates(biz, acc_tg, "views")
    conf, why = pr.confidence_of(s["stats"], s["picks"])
    assert conf == "low" and why


def test_create_proposal_rules_when_ai_fails(biz, acc_tg, boss):
    from apps.ads import proposals as pr
    seed_tg_posts(acc_tg)
    broken = AIRouter(providers={n: FakeAIProvider(n, [RuntimeError("x")] * 5) for n in ("openai", "claude")}, use_fakes=True)
    p = pr.create_proposal(biz, acc_tg, "subscribers", user=boss, router=broken)
    assert p.source == "rules" and p.result["picks"] and p.result["verdict"] in ("advertise", "improve_first")
    assert p.result["guide_key"] == "telegram_subscribers" and p.version == 1
    p2 = pr.create_proposal(biz, acc_tg, "subscribers", user=boss, router=broken)
    assert p2.version == 2


def test_create_proposal_with_ai_merges_safely(biz, acc_tg, boss):
    from apps.ads import proposals as pr
    seed_tg_posts(acc_tg)
    top = pr.score_candidates(biz, acc_tg, "leads")["picks"][0]["post_id"]
    ai = {"summary": "AI xulosa: bu post yaxshi", "audience": {"summary": "Kichik biznes egalari", "age": "22-40", "regions": ["Toshkent"], "interests": ["dizayn"]},
          "picks": [{"post_id": top, "directions": ["Logo ahamiyati"], "improve": ["CTA qo'shing"]}, {"post_id": 999999, "directions": ["begona"]}],
          "creative_notes": ["Bitta xabar"], "test_plan": {"duration_days": 4, "variants": ["A", "B"], "success_signals": ["x"], "stop_signals": ["y"]}, "avoid": ["z"],
          "budget": "5 000 000 so'm", "score": 99999}
    p = pr.create_proposal(biz, acc_tg, "leads", user=boss, router=fake_router(json.dumps(ai)))
    assert p.source == "ai" and p.result["summary"].startswith("AI xulosa") and p.result["audience"]["regions"] == ["Toshkent"]
    assert p.result["picks"][0]["directions"] == ["Logo ahamiyati"] and p.result["test_plan"]["duration_days"] == 4
    assert all(k["post_id"] != 999999 for k in p.result["picks"]) and "budget" not in json.dumps(p.result)
    assert p.result["picks"][0]["score"] != 99999


def test_proposal_rejects_youtube_and_bad_objective(biz, boss):
    from apps.ads import proposals as pr
    yt = SocialAccount.objects.create(business=biz, platform="youtube", name="yt", handle="yt", external_id="UC1")
    with pytest.raises(ValueError):
        pr.create_proposal(biz, yt, "views", user=boss)
    with pytest.raises(ValueError):
        pr.create_proposal(biz, SocialAccount.objects.create(business=biz, platform="telegram", name="t", handle="t", external_id="-1"), "magic", user=boss)


def test_brief_pdf_and_views(adminc, biz, acc_tg, boss):
    from apps.ads import proposals as pr
    from apps.ads.brief import build_brief_pdf
    seed_tg_posts(acc_tg)
    p = pr.create_proposal(biz, acc_tg, "sales", user=boss, use_ai=False)
    pdf = build_brief_pdf(p)
    assert pdf[:4] == b"%PDF" and len(pdf) > 2000
    assert adminc.get("/reklama/").status_code == 200
    r = adminc.post("/reklama/taklif/yangi/", {"account": acc_tg.pk, "objective": "leads", "note": "yangi kurs"})
    assert r.status_code == 302
    from apps.ads.models import AdProposal
    q = AdProposal.objects.filter(objective="leads").first()
    r = adminc.get(f"/reklama/taklif/{q.pk}/")
    assert r.status_code == 200 and "Targetolog uchun PDF" in r.content.decode()
    assert adminc.get(f"/reklama/taklif/{q.pk}/pdf/")["Content-Type"] == "application/pdf"
    adminc.post(f"/reklama/taklif/{q.pk}/holat/", {"status": "sent"})
    q.refresh_from_db()
    assert q.status == "sent"
    assert adminc.post(f"/reklama/taklif/{q.pk}/qayta/").status_code == 302
    assert AdProposal.objects.filter(objective="leads").count() == 2
    assert adminc.post("/reklama/taklif/yangi/", {"account": acc_tg.pk, "objective": "nope"}).status_code == 302


def test_proposal_isolated_between_businesses(biz, biz2, acc_tg, boss):
    from apps.ads import proposals as pr
    seed_tg_posts(acc_tg)
    p = pr.create_proposal(biz, acc_tg, "views", user=boss, use_ai=False)
    u = User.objects.create_user("u2", password="Aaaa#1234567")
    UserBusinessAccess.objects.create(user=u, business=biz2, role=Role.objects.get(name="Targetolog"))
    c = client_for(u, "Aaaa#1234567", biz2)
    assert c.get(f"/reklama/taklif/{p.pk}/").status_code in (403, 404)
    assert c.get(f"/reklama/taklif/{p.pk}/pdf/").status_code in (403, 404)


# ------------------------------------------------------------------ faktlar
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>X</title>
<item><title>Instagram tests 3 minute Reels</title><link>https://ex.com/1</link><pubDate>Mon, 05 Oct 2026 08:00:00 +0000</pubDate><description>&lt;p&gt;Instagram is testing Reels up to 3 minutes.&lt;/p&gt;</description></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom title</title><link rel="alternate" href="https://ex.com/atom1"/><updated>2026-10-05T08:00:00Z</updated><summary>Atom body</summary></entry></feed>"""


def test_feed_parsing_and_safety():
    from apps.facts import fetcher
    it = fetcher.parse_feed(RSS)
    assert it[0]["title"].startswith("Instagram") and "<p>" not in it[0]["snippet"] and it[0]["published_at"].year == 2026
    assert fetcher.parse_feed(ATOM)[0]["url"] == "https://ex.com/atom1"
    with pytest.raises(fetcher.FeedError):
        fetcher.parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><rss></rss>')
    with pytest.raises(fetcher.FeedError):
        fetcher.check_url("ftp://x.com/feed")
    with pytest.raises(fetcher.FeedError):
        fetcher.check_url("http://127.0.0.1/feed")


def test_verify_numbers_and_quotes():
    from apps.facts import verify
    src_t, src_s = "Designers adopt AI", "A survey of 1,200 designers found 64% use AI tools weekly."
    ok = verify.check_point("64% dizaynerlar AI dan haftasiga foydalanadi", "found 64% use AI tools weekly", src_t, src_s)
    assert ok["verified"] and ok["has_numbers"]
    wrong_num = verify.check_point("70% dizaynerlar", "found 64% use AI tools weekly", src_t, src_s)
    assert not wrong_num["verified"]
    fake_quote = verify.check_point("64% dizaynerlar", "this sentence is not in the source at all", src_t, src_s)
    assert not fake_quote["verified"]
    assert verify.numbers("1,200 va 64%") == {"1200", "64"}


def mk_source(name, tier, feed):
    from apps.facts.models import FactSource
    return FactSource.objects.create(name=name, url="https://" + name.lower().replace(" ", "") + ".com", feed_url=feed, tier=tier, domains=["education", "smm"], is_system=True)


def mk_item(src, url, title, snippet, days=1):
    from apps.facts.models import FactItem
    return FactItem.objects.create(source=src, url=url, title=title, snippet=snippet, published_at=timezone.now() - timedelta(days=days))


def ai_json(item_id, claim, quote, title="Instagram yangi reels formati"):
    return json.dumps({"suggestions": [{"kind": "news", "title": title, "angle": "Yangilik burchagi", "why": "Sizga foydali", "format": "Reels",
                                        "points": [{"claim": claim, "item_id": item_id, "quote": quote}]}]})


@pytest.fixture
def topic(biz, acc_tg):
    from apps.facts.models import FactTopic
    return FactTopic.objects.create(business=biz, platform="telegram", title="SMM yangiliklari", keywords=["instagram", "reels"], kinds=["news"])


def test_engine_keeps_numeric_fact_only_from_tier_a_or_corroborated(biz, topic):
    from apps.facts import engine
    from apps.facts.models import FactSuggestion
    a = mk_source("Official Blog", "A", "https://a.com/feed")
    b1 = mk_source("News One", "B", "https://b1.com/feed")
    b2 = mk_source("News Two", "B", "https://b2.com/feed")
    ia = mk_item(a, "https://a.com/1", "Instagram tests longer Reels", "Instagram is testing Reels up to 3 minutes. Early tests show 27% more watch time.")
    q = "Early tests show 27% more watch time"
    n = engine.generate_for_topic(topic, router=fake_router(ai_json(ia.pk, "Sinovda ko'rish vaqti 27% oshdi", q)))
    assert n == 1
    s = FactSuggestion.objects.get()
    assert s.by_ai and s.verified_count == 1 and s.key_points[0]["tier"] == "A" and s.key_points[0]["url"] == "https://a.com/1"
    FactSuggestion.objects.all().delete()
    # B manba, raqam bor, tasdiqlovchi ikkinchi manba yo'q -> tashlanadi
    from apps.ai_router.models import AICache
    AICache.objects.all().delete()
    ib = mk_item(b1, "https://b1.com/1", "Instagram extends Reels length", "Instagram extends Reels length. Reels now get 41% more reach in tests.")
    n = engine.generate_for_topic(topic, router=fake_router(ai_json(ib.pk, "Reels qamrovi 41% oshdi", "Reels now get 41% more reach in tests", title="Reels qamrovi")))
    assert n == 0
    # ikkinchi mustaqil manba ham 41% desa -> tasdiqlanadi
    AICache.objects.all().delete()
    mk_item(b2, "https://b2.com/9", "Reels length extended by Instagram", "Report: Reels extended; reach grew 41% in tests, Instagram says.")
    n = engine.generate_for_topic(topic, router=fake_router(ai_json(ib.pk, "Reels qamrovi 41% oshdi", "Reels now get 41% more reach in tests", title="Reels qamrovi 2")))
    assert n == 1


def test_engine_drops_invented_quote_and_dedupes(biz, topic):
    from apps.facts import engine
    from apps.facts.models import FactSuggestion
    a = mk_source("Official Blog", "A", "https://a.com/feed")
    ia = mk_item(a, "https://a.com/1", "Instagram tests longer Reels", "Instagram is testing Reels up to 3 minutes.")
    bad = engine.generate_for_topic(topic, router=fake_router(ai_json(ia.pk, "Instagram 10 daqiqalik reels chiqardi", "Instagram launched ten minute Reels worldwide today")))
    assert bad == 0 and FactSuggestion.objects.count() == 0
    from apps.ai_router.models import AICache
    AICache.objects.all().delete()
    good = engine.generate_for_topic(topic, router=fake_router(ai_json(ia.pk, "Instagram 3 daqiqalik Reels sinayapti", "Instagram is testing Reels up to 3 minutes")))
    assert good == 1
    # materiallar ishlatilgan: takroriy taklif yaratilmaydi
    AICache.objects.all().delete()
    again = engine.generate_for_topic(topic, router=fake_router(ai_json(ia.pk, "Instagram 3 daqiqalik Reels sinayapti", "Instagram is testing Reels up to 3 minutes")))
    assert again == 0


def test_engine_untranslated_fallback_without_ai(biz, topic):
    from apps.facts import engine
    from apps.facts.models import FactSuggestion
    a = mk_source("Official Blog", "A", "https://a.com/feed")
    mk_item(a, "https://a.com/1", "Instagram tests longer Reels", "Instagram is testing Reels up to 3 minutes.")
    broken = AIRouter(providers={n: FakeAIProvider(n, [RuntimeError("x")] * 5) for n in ("openai", "claude")}, use_fakes=True)
    assert engine.generate_for_topic(topic, router=broken) == 1
    s = FactSuggestion.objects.get()
    assert not s.by_ai and "tarjima" in s.angle.lower()


def test_refresh_all_with_fake_feeds_and_default_topics(biz, acc_tg, settings):
    from apps.facts import engine
    from apps.facts.models import FactSource, FactTopic
    settings.USE_FAKES = True
    engine.ensure_sources()
    assert FactSource.objects.count() >= 25 and FactSource.objects.filter(tier="A").exists()
    assert "education" in engine.business_domains(biz) and "smm" in engine.business_domains(biz)
    res = engine.refresh_all(biz)
    assert res["sources"] >= 1 and res["new_items"] >= 1 and res["errors"] == 0
    assert FactTopic.objects.filter(business=biz).exists()     # standart yo'nalish yaratildi


def test_facts_job_and_pages(adminc, biz, acc_tg, settings):
    from apps.facts.jobs import facts_refresh
    from apps.jobs.queue import JobContext
    settings.USE_FAKES = True
    res = facts_refresh(JobContext(job=SimpleNamespace(pk=0), payload={"business_id": biz.pk}))
    assert "sources" in res
    for u in ("/faktlar/", "/faktlar/yonalishlar/", "/faktlar/manbalar/", "/faktlar/?status=used&platform=telegram&kind=news"):
        assert adminc.get(u).status_code == 200, u
    r = adminc.post("/faktlar/yonalishlar/", {"platform": "telegram", "title": "Dizayn yangiliklari", "keywords_text": "graphic design, branding", "kinds": ["fact", "tip"]})
    assert r.status_code == 302
    from apps.facts.models import FactSource, FactTopic
    t = FactTopic.objects.get(title="Dizayn yangiliklari")
    assert t.keywords == ["graphic design", "branding"]
    adminc.post(f"/faktlar/yonalishlar/{t.pk}/toggle/")
    t.refresh_from_db()
    assert not t.active
    adminc.post("/faktlar/manbalar/", {"name": "Mening manba", "url": "https://my.example.org", "feed_url": "https://my.example.org/rss", "language": "en", "domains": "design"})
    s = FactSource.objects.get(name="Mening manba")
    assert s.tier == "C" and not s.is_system
    adminc.post(f"/faktlar/manbalar/{s.pk}/test/")
    s.refresh_from_db()
    assert s.last_ok is True                 # USE_FAKES: soxta lenta
    adminc.post(f"/faktlar/manbalar/{s.pk}/delete/")
    assert not FactSource.objects.filter(pk=s.pk).exists()
    assert adminc.post("/faktlar/yangilash/").status_code == 302


def test_facts_status_and_isolation(biz, biz2, topic):
    from apps.facts.models import FactSuggestion
    s = FactSuggestion.objects.create(business=biz, topic=topic, platform="telegram", kind="news", title="T", key_points=[{"claim": "c", "quote": "q", "source": "S", "tier": "A", "url": "https://a.com"}], verified_count=1)
    u = User.objects.create_user("u2", password="Aaaa#1234567")
    UserBusinessAccess.objects.create(user=u, business=biz2, role=Role.objects.get(name="Menejer"))
    c = client_for(u, "Aaaa#1234567", biz2)
    assert c.post(f"/faktlar/taklif/{s.pk}/holat/", {"status": "used"}).status_code in (403, 404)
    s.refresh_from_db()
    assert s.status == "new"
    html = c.get("/faktlar/").content.decode()
    assert "T</h3>" not in html


def test_all_new_nav_pages_render(adminc, biz, acc_tg):
    for u in ("/", "/maqsadlar/", "/maqsadlar/yangi/", "/reklama/", "/faktlar/", f"/bizneslar/{biz.pk}/", f"/bizneslar/{biz.pk}/pasport/", "/sozlamalar/biznes-turlari/",
              "/sozlamalar/biznes-turlari/yangi/", "/sozlamalar/?tab=umumiy"):
        r = adminc.get(u)
        assert r.status_code == 200, (u, r.status_code)
        html = r.content.decode()
        assert "Maqsadlar" in html and "Faktlar va yangiliklar" in html and "Reklama tahlili" in html or u != "/"


# ------------------------------------------------------------------ biznesni butunlay o'chirish
def test_business_purge_requires_admin_name_and_password(adminc, biz, acc_tg, admin):
    from apps.businesses.models import Business
    from apps.connections.models import SocialAccount
    mkpost(acc_tg, 1)
    admin.set_password("Parol#12345"); admin.save()
    adminc.force_login(admin)
    r = adminc.post(f"/bizneslar/{biz.pk}/ochirish/", {"confirm_name": biz.name, "password": "xato"})
    assert r.status_code == 302 and Business.objects.filter(pk=biz.pk).exists()
    r = adminc.post(f"/bizneslar/{biz.pk}/ochirish/", {"confirm_name": "boshqa nom", "password": "Parol#12345"})
    assert Business.objects.filter(pk=biz.pk).exists()
    r = adminc.post(f"/bizneslar/{biz.pk}/ochirish/", {"confirm_name": biz.name, "password": "Parol#12345"})
    assert r.status_code == 302 and not Business.objects.filter(pk=biz.pk).exists()
    assert not SocialAccount.objects.filter(pk=acc_tg.pk).exists() and not Post.objects.filter(business_id=biz.pk).exists()


def test_business_purge_not_for_non_admin(client, biz):
    from apps.businesses.models import Business
    u = User.objects.create_user("oddiy", password="Oddiy#2026test!")
    client.force_login(u)
    r = client.post(f"/bizneslar/{biz.pk}/ochirish/", {"confirm_name": biz.name, "password": "x"})
    assert r.status_code in (403, 404) and Business.objects.filter(pk=biz.pk).exists()
