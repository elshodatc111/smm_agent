import gzip
import logging
import os
import shutil
import subprocess
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.notify import notify
from apps.core.settings_store import get_setting
from apps.jobs.queue import JobContext, register_handler

from . import services
from .models import BackupRecord, HealthSnapshot

log = logging.getLogger(__name__)


@register_handler("health_probe", "system")
def health_probe(ctx: JobContext):
    snap = services.snapshot()
    slim = {k: v for k, v in snap.items() if k in ("server", "queue", "r2", "tips")}
    slim["queue"] = {**slim["queue"], "heartbeat": str(slim["queue"].get("heartbeat"))}
    HealthSnapshot.objects.create(data=slim)
    HealthSnapshot.objects.filter(at__lt=timezone.now() - timedelta(days=14)).delete()
    if snap["server"]["disk_pct"] > 92:
        notify("quota.warning", "Disk deyarli to'lgan", f"{snap['server']['disk_pct']}%", severity="warn", dedupe_key="disk-full")
    return {"tips": len(snap["tips"])}


def find_dump_tool() -> str | None:
    """mysqldump ni PATH dan, bo'lmasa Windows dagi odatiy o'rnatish papkalaridan topadi."""
    import glob
    exe = shutil.which("mysqldump") or shutil.which("mariadb-dump")
    if exe:
        return exe
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 "/usr/local/mysql/bin", "/opt/homebrew/bin"):
        for pat in (os.path.join(base, "MySQL", "*", "bin", "mysqldump.exe"), os.path.join(base, "MariaDB *", "bin", "mariadb-dump.exe"),
                    os.path.join(base, "MariaDB *", "bin", "mysqldump.exe"), os.path.join(base, "mysqldump")):
            hit = sorted(glob.glob(pat))
            if hit:
                return hit[-1]
    return None


def run_backup() -> BackupRecord:
    d = settings.BASE_DIR / get_setting("backup.dir", "backups")
    d.mkdir(exist_ok=True)
    stamp = timezone.now().strftime("%Y%m%d_%H%M")
    db = settings.DATABASES["default"]
    try:
        if "sqlite" in db["ENGINE"]:
            out = d / f"smm_{stamp}.sqlite3.gz"
            with open(db["NAME"], "rb") as src, gzip.open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
        else:
            exe = find_dump_tool()
            if not exe:
                raise RuntimeError("mysqldump topilmadi (MySQL bin papkasini PATH ga qo'shing)")
            out = d / f"smm_{stamp}.sql.gz"
            env = {**os.environ, "MYSQL_PWD": db.get("PASSWORD", "")}
            p = subprocess.run([exe, "-h", db.get("HOST", "127.0.0.1"), "-P", str(db.get("PORT", 3306)), "-u", db["USER"],
                                "--single-transaction", "--routines", "--default-character-set=utf8mb4", db["NAME"]],
                               capture_output=True, env=env, timeout=1800)
            if p.returncode != 0:
                raise RuntimeError(p.stderr.decode(errors="replace")[:300])
            with gzip.open(out, "wb") as f:
                f.write(p.stdout)
        envf = settings.BASE_DIR / ".env"
        if envf.exists():
            shutil.copy(envf, d / f"env_{stamp}.backup")  # FERNET_KEYS shu yerda: alohida joyga ham nusxa oling!
        keep = timedelta(days=int(get_setting("backup.keep_days", 14)))
        for f in d.iterdir():
            if f.is_file() and timezone.now().timestamp() - f.stat().st_mtime > keep.total_seconds():
                f.unlink()
        return BackupRecord.objects.create(path=str(out), size=out.stat().st_size)
    except Exception as e:  # noqa: BLE001
        notify("job.failed", "Zaxira nusxa xatosi", str(e)[:300], severity="critical", dedupe_key="backup-fail")
        return BackupRecord.objects.create(path="", ok=False, note=str(e)[:300])


@register_handler("backup_db", "system")
def backup_db(ctx: JobContext):
    r = run_backup()
    if not r.ok:
        raise RuntimeError(r.note)
    return {"path": r.path, "size": r.size}


@register_handler("anomaly_scan", "system")
def anomaly_scan(ctx: JobContext):
    from apps.connections.models import SocialAccount
    from apps.metrics.analytics import detect_anomalies
    n = 0
    for a in SocialAccount.objects.filter(status__in=["active", "token_expiring"], archived_at__isnull=True):
        an = detect_anomalies(a)
        if an:
            notify("anomaly.detected", f"Keskin {an['direction']}: {a.name}", f"Obunachi o'zgarishi {an['delta']:+d} (z={an['z']:.1f})",
                   business_id=a.business_id, severity="warn", dedupe_key=f"anom:{a.pk}:{timezone.now():%Y%m%d}")
            n += 1
    return {"anomalies": n}


@register_handler("smart_alerts", "system")
def smart_alerts(ctx: JobContext):
    from apps.core import alerts
    return alerts.run_all()
