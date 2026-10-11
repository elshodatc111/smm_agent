"""Tizim holati (real vaqt) + o'zi sozlamaga tavsiya (TZ 4.16)."""
from __future__ import annotations

import shutil
import subprocess
import time
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.models import Count, Max
from django.utils import timezone

from apps.core.settings_store import get_setting

_START = time.time()


def server() -> dict:
    out = {"uptime_h": round((time.time() - _START) / 3600, 1), "db": connection.vendor}
    try:
        import psutil
        out.update(cpu=psutil.cpu_percent(interval=0.2), ram=psutil.virtual_memory().percent)
    except Exception:  # noqa: BLE001
        out.update(cpu=None, ram=None)
    du = shutil.disk_usage(settings.BASE_DIR)
    out["disk_pct"] = round(du.used / du.total * 100, 1)
    out["disk_free_gb"] = round(du.free / 1e9, 1)
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            u, mu, mt = (float(x) for x in r.stdout.strip().split("\n")[0].split(","))
            out["gpu"] = {"util": u, "vram_used_mb": mu, "vram_total_mb": mt}
    except Exception:  # noqa: BLE001
        out["gpu"] = None
    try:
        connection.ensure_connection()
        out["db_ok"] = True
    except Exception:  # noqa: BLE001
        out["db_ok"] = False
    return out


def queue() -> dict:
    from apps.jobs.models import Job, WorkerHeartbeat
    c = {r["status"]: r["n"] for r in Job.objects.values("status").annotate(n=Count("id"))}
    oldest = Job.objects.filter(status="pending", run_at__lte=timezone.now()).order_by("run_at").first()
    beat = WorkerHeartbeat.objects.aggregate(m=Max("beat_at"))["m"]
    alive = bool(beat and beat > timezone.now() - timedelta(seconds=60))
    return {"counts": c, "oldest_wait_min": round((timezone.now() - oldest.run_at).total_seconds() / 60, 1) if oldest else 0,
            "worker_alive": alive, "heartbeat": beat,
            "failed_24h": Job.objects.filter(status="failed", finished_at__gte=timezone.now() - timedelta(days=1)).count()}


def providers() -> list[dict]:
    from apps.providers.impl import ScrapeCreatorsProvider  # noqa: F401
    from apps.providers.models import FailoverEvent, ProviderState, ProviderUsageLog
    from apps.providers.quota import days_left, youtube_quota_used
    rows = []
    since = timezone.now() - timedelta(days=1)
    for name in ("youtube_data_api", "scrapecreators", "tme_public"):
        st = ProviderState.objects.filter(name=name).first()
        logs = ProviderUsageLog.objects.filter(provider=name, at__gte=since)
        n, err = logs.count(), logs.filter(ok=False).count()
        status = "good"
        if st and st.cooldown_until and st.cooldown_until > timezone.now():
            status = "cooldown"
        elif n and err / n > 0.3:
            status = "error"
        row = {"name": name, "status": status, "last_ok": st.last_ok_at if st else None, "latency_ms": st.avg_latency_ms if st else None,
               "requests_24h": n, "error_pct": round(100 * err / n, 1) if n else 0, "last_error": st.last_error if st else ""}
        if name == "youtube_data_api":
            lim = float(get_setting("providers.youtube_data_api.daily_quota", 10000))
            row["remaining"] = f"{lim - youtube_quota_used():.0f} / {lim:.0f} birlik"
        elif name == "scrapecreators":
            row["remaining"] = f"{st.credits_remaining:.0f} kredit" if st and st.credits_remaining is not None else "noma'lum"
            dl = days_left(name)
            row["days_left"] = round(dl, 1) if dl else None
            row["mode"] = get_setting("scrapecreators.mode", "free")
        rows.append(row)
    ev = FailoverEvent.objects.first()
    if ev:
        rows[0]["last_switch"] = f"{ev.from_provider}→{ev.to_provider}: {ev.reason}"
    return rows


def ai() -> list[dict]:
    from apps.ai_router.models import AIKey, AIUsageLog
    out = []
    since = timezone.now() - timedelta(days=1)
    for prov in ("openai", "claude"):
        keys = AIKey.objects.filter(provider=prov)
        logs = AIUsageLog.objects.filter(provider=prov, at__gte=since)
        n = logs.count()
        out.append({"name": prov, "keys": keys.count(), "active_keys": keys.filter(enabled=True).count(),
                    "cooldown": keys.filter(cooldown_until__gt=timezone.now()).count(), "requests_24h": n,
                    "errors": logs.filter(ok=False).count(), "tokens": sum(l.tokens_in + l.tokens_out for l in logs[:500]),
                    "enabled": keys.filter(enabled=True).exists()})
    return out


def connections() -> list[dict]:
    from apps.connections.models import SocialAccount
    return [{"id": a.pk, "name": str(a), "business": a.business.name, "status": a.status, "expires": a.token_expires_at,
             "last_collect": a.last_collect_at, "error": a.last_error} for a in SocialAccount.objects.filter(archived_at__isnull=True).select_related("business")]


def r2() -> dict:
    from apps.content.models import TempObject
    from apps.content.temphost import r2_used_bytes
    cap = float(get_setting("publish.r2.max_gb", 9)) * 1024 ** 3
    used = r2_used_bytes()
    return {"used_gb": round(used / 1024 ** 3, 2), "cap_gb": cap / 1024 ** 3, "pct": round(100 * used / cap, 1) if cap else 0,
            "files": TempObject.objects.filter(status="uploaded").count()}


def worker_link() -> dict:
    """Cloudflare Worker (vaqtinchalik fayl serveri) sozlanganmi."""
    return {"configured": bool(get_setting("worker.cloudflare_url", "")), "ok": None, "clicks_today": 0, "limit": 0, "message": ""}


def recommendations(snap: dict) -> list[str]:
    tips = []
    for p in snap["providers"]:
        if p["name"] == "scrapecreators" and p.get("days_left") and p["days_left"] < 7:
            tips.append(f"ScrapeCreators krediti ~{p['days_left']} kunda tugaydi: yig'ish chastotasini kamaytiring yoki kredit sotib oling.")
        if p["name"] == "youtube_data_api":
            from apps.providers.quota import youtube_quota_pct
            if youtube_quota_pct() > 80:
                tips.append("YouTube kvotasi 80% dan oshdi: raqobatchi yig'ishni kamaytiring (avtomatik ScrapeCreators'ga o'tadi).")
    for c in snap["connections"]:
        if c["status"] in ("error", "token_expiring"):
            tips.append(f"{c['name']}: {c['error'] or 'token muddati tugayapti'} — Ulanishlar bo'limidan qayta ulang.")
    if snap["r2"]["pct"] > 80:
        tips.append("R2 hajmi 80% dan oshdi: tozalash vazifasini tekshiring.")
    if not snap["queue"]["worker_alive"]:
        tips.append("Worker jarayoni javob bermayapti: run.bat orqali qayta ishga tushiring (watchdog yoqilganmi?).")
    if snap["server"]["disk_pct"] > 90:
        tips.append("Disk 90% dan ortiq to'lgan: eski media/zaxira fayllarni tozalang.")
    if snap["queue"]["failed_24h"] > 10:
        tips.append("So'nggi 24 soatda ko'p vazifa xato bergan: Navbat bo'limidagi xatolarni ko'ring.")
    if not get_setting("worker.cloudflare_url", ""):
        tips.append("Cloudflare Worker ulanmagan: qisqa havola, Instagram rasm nashri va OAuth uchun kerak.")
    return tips


def snapshot() -> dict:
    snap = {"server": server(), "queue": queue(), "providers": providers(), "ai": ai(), "connections": connections(),
            "r2": r2(), "worker": worker_link()}
    snap["tips"] = recommendations(snap)
    return snap
