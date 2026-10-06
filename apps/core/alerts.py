"""Aqlli ogohlantirishlar: har 30 daqiqada tekshiriladi, har biri sozlanadi (yoqish/o'chirish va chegara)."""
from __future__ import annotations

import logging
import shutil
import statistics
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .notify import notify
from .settings_store import get_setting, set_setting
from .utils import tz

log = logging.getLogger(__name__)


def A(biz, key, title, body, sev="warn", link="", days=1):
    return {"biz": biz, "key": key, "title": title, "body": body, "sev": sev, "link": link, "days": days}


# --------------------------------------------------------------------- tekshiruvlar (har biri yield A(...))
def d_followers_drop(b, p):
    from apps.metrics.models import AccountMetrics
    now = timezone.now()
    for acc in b.accounts.filter(archived_at__isnull=True):
        cur = AccountMetrics.objects.filter(account=acc, followers__isnull=False).order_by("-taken_at").first()
        old = AccountMetrics.objects.filter(account=acc, followers__isnull=False, taken_at__lte=now - timedelta(days=7)).order_by("-taken_at").first()
        if cur and old and old.followers > 50:
            pct = (cur.followers - old.followers) / old.followers * 100
            if pct <= -p:
                yield A(b.pk, f"fd:{acc.pk}", f"Obunachi kamaymoqda: {acc.name}", f"7 kunda {old.followers} → {cur.followers} ({pct:.1f}%). Oxirgi postlar va izohlarni tekshiring.", "warn", "/tahlil/")


def d_followers_surge(b, p):
    from apps.metrics.models import DailyStat
    for ds in DailyStat.objects.filter(business=b, account__isnull=False, day__gte=timezone.localdate() - timedelta(days=1)).select_related("account"):
        if ds.followers and ds.followers_delta and ds.followers_delta / max(ds.followers - ds.followers_delta, 1) * 100 >= p:
            yield A(b.pk, f"fs:{ds.account_id}:{ds.day}", f"Obunachi tez o'syapti: {ds.account.name}", f"{ds.day}: +{ds.followers_delta} obunachi. Qaysi post sabab bo'lganini «Tahlil» da ko'ring va takrorlang.", "info", "/tahlil/", 2)


def d_no_posts(b, p):
    from apps.metrics.models import Post
    for acc in b.accounts.filter(archived_at__isnull=True, status__in=["active", "token_expiring"]):
        last = Post.objects.filter(account=acc).order_by("-published_at").first()
        if last and last.published_at < timezone.now() - timedelta(days=p):
            yield A(b.pk, f"np:{acc.pk}", f"{int(p)} kundan beri post yo'q: {acc.name}", f"Oxirgi post: {last.published_at:%d.%m.%Y}. Muntazam nashr algoritmda ko'rinishni saqlaydi.", "warn", "/kalendar/yangi/")


def d_empty_schedule(b, p):
    from apps.content.models import ContentItem
    if timezone.localtime(timezone.now(), tz()).hour < 9 or not b.accounts.filter(archived_at__isnull=True).exists():
        return
    now = timezone.now()
    n = ContentItem.objects.filter(business=b, status__in=["scheduled", "draft"], scheduled_at__gte=now, scheduled_at__lte=now + timedelta(days=p)).count()
    if n == 0:
        yield A(b.pk, f"es:{timezone.localdate()}", f"Keyingi {int(p)} kunga post rejalashtirilmagan: {b.name}", "Kalendar bo'sh. «G'oyalar banki» dan g'oya olib tez post qo'shing.", "warn", "/goyalar/", 1)


def d_token(b, p):
    now = timezone.now()
    for acc in b.accounts.filter(archived_at__isnull=True, token_expires_at__isnull=False).exclude(platform="youtube"):
        if acc.token_expires_at < now + timedelta(days=p):
            left = (acc.token_expires_at - now).days
            yield A(b.pk, f"tk:{acc.pk}", f"Ulanish tugayapti: {acc.name}", f"{max(left, 0)} kun qoldi. «Ulanishlar» da qayta ulang, aks holda nashr to'xtaydi.", "critical" if left <= 2 else "warn", f"/ulanishlar/{acc.pk}/")


def d_stuck_publish(b, p):
    from apps.content.models import ContentItem
    for it in ContentItem.objects.filter(business=b, status="scheduled", scheduled_at__lt=timezone.now() - timedelta(minutes=p)):
        yield A(b.pk, f"sp:{it.pk}", f"Nashr vaqti o'tdi, post chiqmadi: {it.title or 'post'}", "Rejalashtirilgan vaqt o'tib ketgan. Ulanish va worker ishlayotganini tekshiring, kerak bo'lsa «Hozir nashr».", "critical", f"/kalendar/{it.pk}/")


def d_engagement_drop(b, p):
    from apps.metrics import analytics as an
    rows = list(an.latest_metrics_qs(b.pk, since=timezone.now() - timedelta(days=30)).exclude(er=None).order_by("-post__published_at"))
    if len(rows) < 8:
        return
    recent, rest = rows[:4], rows[4:]
    base = statistics.median([r.er for r in rest])
    cur = statistics.mean([r.er for r in recent])
    if base > 0 and cur < base * (1 - p / 100):
        yield A(b.pk, f"ed:{timezone.localdate():%G%V}", f"Faollik pasaymoqda: {b.name}", f"Oxirgi 4 post ER {cur * 100:.1f}% — oldingi median {base * 100:.1f}% (−{(1 - cur / base) * 100:.0f}%). Format va vaqtni qayta ko'rib chiqing.", "warn", "/tahlil/", 3)


def d_story_drop(b, p):
    from apps.metrics.models import DailyStat
    qs = list(DailyStat.objects.filter(business=b, account__isnull=True, day__gte=timezone.localdate() - timedelta(days=17)).order_by("day"))
    cur = [x.story_views for x in qs[-3:] if x.stories]
    old = [x.story_views / x.stories for x in qs[:-3] if x.stories]
    if len(cur) >= 2 and len(old) >= 4:
        c = statistics.mean([x.story_views / max(x.stories, 1) for x in qs[-3:] if x.stories])
        o = statistics.mean(old)
        if o > 0 and c < o * (1 - p / 100):
            yield A(b.pk, f"sd:{timezone.localdate():%G%V}", f"Stories ko'rishlari tushdi: {b.name}", f"Bir story o'rtacha {c:.0f} ko'rish (oldin {o:.0f}). So'rovnoma/stiker qo'shing, soatni almashtiring.", "warn", "/tahlil/", 3)


def d_negative(b, p):
    from apps.metrics.models import Comment
    n = Comment.objects.filter(business=b, sentiment="negative", created_at__gte=timezone.now() - timedelta(hours=24)).count()
    if n >= p:
        yield A(b.pk, f"ng:{timezone.localdate()}", f"Salbiy izohlar ko'paydi ({n} ta / 24 soat): {b.name}", "Izohlarni ko'rib chiqing va javob bering — tez javob obro'ni saqlaydi.", "warn", "/studiya/izohlar/")


def d_stale_collect(b, p):
    now = timezone.now()
    for acc in b.accounts.filter(archived_at__isnull=True, status="active"):
        if acc.last_collect_at and acc.last_collect_at < now - timedelta(hours=p):
            yield A(b.pk, f"sc:{acc.pk}", f"Ma'lumot yig'ilmayapti: {acc.name}", f"Oxirgi yig'ish: {acc.last_collect_at:%d.%m %H:%M}. {acc.last_error[:150]}", "warn", f"/ulanishlar/{acc.pk}/")


def d_plan_behind(b, p):
    from apps.content.models import ContentItem
    from apps.studio.models import ContentPlan
    today = timezone.localdate()
    pl = ContentPlan.objects.filter(business=b, month=today.replace(day=1), loaded_to_calendar=True).first()
    if not pl:
        return
    due = len([e for e in pl.entries if e.get("date", "9999") < today.isoformat()])
    done = ContentItem.objects.filter(business=b, plan=pl, status="published").count()
    if due - done >= p:
        yield A(b.pk, f"pb:{pl.pk}:{today:%G%V}", f"Kontent-reja orqada: {b.name}", f"Rejaga ko'ra {due} ta post chiqishi kerak edi, chiqqani {done}. Qolgan postlarni tezlashtiring.", "warn", "/kalendar/", 3)


def d_draft_pile(b, p):
    from apps.content.models import ContentItem
    n = ContentItem.objects.filter(business=b, status="draft", scheduled_at__isnull=True, created_at__lt=timezone.now() - timedelta(days=7)).count()
    if n >= p:
        yield A(b.pk, f"dp:{timezone.localdate():%G%V}", f"{n} ta qoralama uzoq vaqtdan beri yotibdi: {b.name}", "Vaqt belgilab chiqaring yoki keraksizini savatga tashlang.", "info", "/kalendar/", 7)


def d_competitor_hit_stale(b, p):
    from apps.connections.models import Competitor
    old = Competitor.objects.filter(business=b, active=True).filter(last_light_at__isnull=True).count()
    if old and not (get_setting("scrapecreators.api_key", "") or get_setting("youtube.api_key", "")):
        yield A(b.pk, "cs", f"Raqobatchi ma'lumot provayderi ulanmagan: {b.name}", "Raqobatchi tahlili provayder (ScrapeCreators / YouTube API) ulangach ishga tushadi. Loyiha ishga tushganda ulang — hozircha g'oyalar o'z tahlilingizdan olinadi.", "info", "/sozlamalar/?tab=xizmatlar", 14)


# global
def g_disk(p):
    try:
        free = shutil.disk_usage(settings.BASE_DIR).free / 1024 ** 3
    except OSError:
        return
    if free < p:
        yield A(None, "disk", f"Diskda joy kam: {free:.1f} GB", "Eski zaxiralar va media fayllarni tozalang, aks holda yuklash va zaxira to'xtashi mumkin.", "critical")


def g_backup(p):
    from apps.health.models import BackupRecord
    last = BackupRecord.objects.filter(ok=True).order_by("-at").first()
    if not last or last.at < timezone.now() - timedelta(hours=p):
        yield A(None, "bk", "Zaxira nusxa eskirgan", "Oxirgi muvaffaqiyatli zaxira " + (f"{last.at:%d.%m %H:%M}" if last else "yo'q") + ". «Tizim holati» da qo'lda zaxira oling.", "warn")


def g_ai(p):
    from apps.ai_router.models import AIUsageLog
    since = timezone.now() - timedelta(hours=2)
    q = AIUsageLog.objects.filter(at__gte=since)
    if q.filter(ok=False).count() >= p and not q.filter(ok=True).exists():
        yield A(None, "ai", "AI xizmati ishlamayapti", "Oxirgi 2 soatda barcha AI so'rovlari xato bilan tugadi. Sozlamalar → AI router → kalitlarni tekshiring.", "critical")


def g_jobs(p):
    from apps.jobs.models import Job
    n = Job.objects.filter(status="failed", finished_at__gte=timezone.now() - timedelta(hours=3)).count()
    if n >= p:
        yield A(None, "jf", f"{n} ta vazifa xato bilan tugadi (3 soat)", "«Tizim → Vazifalar» da xatolarni ko'ring va kerakli bo'lsa qayta urining.", "warn", "/tizim/vazifalar/")


def g_worker(p):
    from apps.jobs.models import WorkerHeartbeat
    last = WorkerHeartbeat.objects.order_by("-beat_at").first()
    if last and last.beat_at < timezone.now() - timedelta(minutes=p):
        yield A(None, "wk", "Fon ishchisi (worker) javob bermayapti", f"Oxirgi signal {last.beat_at:%H:%M}. Rejalashtirilgan postlar chiqmaydi! run.bat ni qayta ishga tushiring.", "critical")


def g_link_worker(p):
    try:
        from apps.links.models import WorkerStatus
        s = WorkerStatus.objects.order_by("-checked_at").first()
    except Exception:  # noqa: BLE001
        return
    if s and not s.ok and get_setting("worker.cloudflare_url", ""):
        yield A(None, "lw", "Qisqa havola Worker ishlamayapti", (s.message or "")[:200], "warn", "/havolalar/")


def g_r2(p):
    from django.db.models import Sum
    from apps.content.models import TempObject
    used = (TempObject.objects.filter(status="uploaded").aggregate(s=Sum("size"))["s"] or 0) / 1024 ** 3
    mx = float(get_setting("publish.r2.max_gb", 9) or 0)
    if mx and used >= mx * p / 100:
        yield A(None, "r2", f"Cloudflare saqlash to'layapti: {used:.1f}/{mx:.0f} GB", "Kerak bo'lmagan fayllarni «Cloudflare» bo'limidan o'chiring (nashr qilinganlarini tozalash tugmasi bor).", "warn", "/cloudflare/")


def g_sqlite(p):
    from django.db import connection
    if connection.vendor != "sqlite":
        return
    import os
    try:
        mb = os.path.getsize(settings.DATABASES["default"]["NAME"]) / 1024 ** 2
    except OSError:
        return
    if mb >= p:
        yield A(None, "sq", f"SQLite bazasi katta ({mb:.0f} MB)", "Tezlik va ishonchlilik uchun MySQL'ga o'tish tavsiya etiladi: mysql_otish.bat (Yo'riqnoma: MySQL'ga o'tish).", "info", "/yoriqnoma/", 30)


# kod, nom, izoh, parametr (nom, standart, birlik), default yoqilgan, funksiya, global?
ALERTS = [
    ("followers_drop", "Obunachi kamayishi", "7 kunda obunachi belgilangan foizdan ko'p kamaysa", ("Chegara", 2, "%"), True, d_followers_drop, False),
    ("followers_surge", "Obunachi keskin o'sishi", "Kunlik o'sish belgilangan foizdan oshsa — sababini bilib takrorlash uchun", ("Chegara", 3, "%"), True, d_followers_surge, False),
    ("no_posts", "Uzoq vaqt post yo'q", "Akkauntda belgilangan kundan beri yangi post chiqmasa", ("Kun", 3, "kun"), True, d_no_posts, False),
    ("empty_schedule", "Kalendar bo'sh", "Keyingi kunlarga hech narsa rejalashtirilmagan bo'lsa", ("Oldinga", 3, "kun"), True, d_empty_schedule, False),
    ("token", "Ulanish muddati tugayapti", "Instagram/Telegram ulanishi tugashiga belgilangan kun qolsa", ("Kun", 7, "kun"), True, d_token, False),
    ("stuck_publish", "Nashr vaqti o'tib ketdi", "Rejalashtirilgan post belgilangan daqiqadan beri chiqmagan bo'lsa", ("Daqiqa", 15, "daqiqa"), True, d_stuck_publish, False),
    ("engagement_drop", "Faollik (ER) pasayishi", "Oxirgi postlar ER i oldingi medianadan belgilangan foizga past bo'lsa", ("Pasayish", 30, "%"), True, d_engagement_drop, False),
    ("story_drop", "Stories ko'rishlari tushishi", "Bir story o'rtacha ko'rishi oldingi davrdan belgilangan foizga past bo'lsa", ("Pasayish", 40, "%"), True, d_story_drop, False),
    ("negative", "Salbiy izohlar ko'payishi", "24 soatda salbiy izohlar soni chegaradan oshsa", ("Soni", 3, "ta"), True, d_negative, False),
    ("stale_collect", "Statistika yig'ilmayapti", "Akkaunt ma'lumoti belgilangan soatdan beri yangilanmasa", ("Soat", 36, "soat"), True, d_stale_collect, False),
    ("plan_behind", "Kontent-reja orqada", "Rejadagi postlar chiqqanidan belgilangan sondan ko'p orqada qolsa", ("Post", 3, "ta"), True, d_plan_behind, False),
    ("draft_pile", "Qoralamalar to'planib qoldi", "Vaqti belgilanmagan 7 kundan eski qoralamalar soni chegaradan oshsa", ("Soni", 10, "ta"), True, d_draft_pile, False),
    ("competitor_provider", "Raqobatchi provayderi ulanmagan", "Raqobatchi qo'shilgan, lekin ma'lumot provayderi kaliti yo'q bo'lsa (loyiha ishga tushganda ulanadi)", None, True, d_competitor_hit_stale, False),
    ("disk", "Diskda joy kam", "Bo'sh joy belgilangan GB dan kam bo'lsa", ("Bo'sh joy", 3, "GB"), True, g_disk, True),
    ("backup", "Zaxira nusxa eskirgan", "Muvaffaqiyatli zaxira belgilangan soatdan eski bo'lsa", ("Soat", 48, "soat"), True, g_backup, True),
    ("ai", "AI xizmati ishlamayapti", "2 soatda barcha AI so'rovlari xato bersa", ("Xato soni", 5, "ta"), True, g_ai, True),
    ("jobs", "Vazifalar xatosi ko'payishi", "3 soatda xato bilan tugagan vazifalar soni chegaradan oshsa", ("Soni", 5, "ta"), True, g_jobs, True),
    ("worker", "Fon ishchisi o'chib qoldi", "Worker signali belgilangan daqiqadan beri kelmasa", ("Daqiqa", 10, "daqiqa"), True, g_worker, True),
    ("link_worker", "Havola Worker ishlamayapti", "Cloudflare Worker tekshiruvi muvaffaqiyatsiz bo'lsa", None, True, g_link_worker, True),
    ("r2", "Cloudflare saqlash to'layapti", "Ishlatilgan hajm limitning belgilangan foizidan oshsa", ("Foiz", 80, "%"), True, g_r2, True),
    ("sqlite", "SQLite bazasi katta", "Baza hajmi chegaradan oshsa MySQL'ga o'tishni tavsiya qiladi", ("Hajm", 500, "MB"), True, g_sqlite, True),
]
BY_CODE = {a[0]: a for a in ALERTS}


def config() -> dict:
    return get_setting("alerts.config", {}) or {}


def is_on(code: str) -> bool:
    c = config().get(code, {})
    return bool(c.get("on", BY_CODE[code][4]))


def param(code: str):
    pr = BY_CODE[code][3]
    if not pr:
        return None
    v = config().get(code, {}).get("p", pr[1])
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(pr[1])


def save_config(data: dict, user=None) -> None:
    cfg = {}
    for code, a in BY_CODE.items():
        row = {"on": bool(data.get(f"on_{code}"))}
        if a[3]:
            try:
                row["p"] = float(str(data.get(f"p_{code}", a[3][1])).replace(",", "."))
            except ValueError:
                row["p"] = a[3][1]
        cfg[code] = row
    set_setting("alerts.config", cfg, user=user)


def run_all(only: str | None = None) -> dict:
    from apps.businesses.models import Business
    sent, errs = 0, 0
    for code, label, desc, pr, _on, fn, glob in ALERTS:
        if only and code != only or not is_on(code):
            continue
        p = param(code)
        try:
            if glob:
                found = list(fn(p))
            else:
                found = []
                for b in Business.objects.all():
                    found += list(fn(b, p))
        except Exception as e:  # noqa: BLE001 — bitta tekshiruv boshqalarni to'xtatmasin
            errs += 1
            log.warning("Alert %s xato: %s", code, e)
            continue
        for a in found:
            sent += notify("alert.smart", a["title"], a["body"], business_id=a["biz"], severity=a["sev"], link=a["link"],
                           dedupe_key=f"alert:{code}:{a['key']}", dedupe_minutes=int(a["days"]) * 24 * 60)
    return {"sent": sent, "errors": errs}
