"""Navbat: enqueue, claim (SELECT ... FOR UPDATE SKIP LOCKED), handler ro'yxati (CONTRACTS §5)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from django.db import connection, transaction
from django.utils import timezone

from apps.core.settings_store import get_setting

from .models import Job, JobLog

log = logging.getLogger(__name__)
BACKOFF_MIN = [1, 5, 15]


@dataclass
class JobContext:
    job: Job
    payload: dict

    def report_progress(self, pct: int) -> None:
        Job.objects.filter(pk=self.job.pk).update(progress=max(0, min(100, int(pct))))

    def log(self, msg: str) -> None:
        JobLog.objects.create(job=self.job, message=str(msg)[:2000])

    def is_cancelled(self) -> bool:
        return Job.objects.filter(pk=self.job.pk, status="cancelled").exists()


_HANDLERS: dict[str, Callable[[JobContext], object]] = {}
_QUEUES: dict[str, str] = {}


def register_handler(job_type: str, queue: str):
    def deco(fn):
        _HANDLERS[job_type] = fn
        _QUEUES[job_type] = queue
        return fn
    return deco


def get_handler(job_type: str):
    return _HANDLERS.get(job_type)


def enqueue(job_type: str, payload: dict | None = None, *, queue: str | None = None, priority: int = 5,
            run_at: datetime | None = None, dedupe_key: str = "", business_id: int | None = None,
            max_attempts: int = 3, dedupe_any_status: bool = False) -> Job | None:
    """dedupe_key berilsa: faol (pending/running) bir xil job bo'lsa yangisini yaratmaydi (None qaytaradi)."""
    if dedupe_key:
        qs = Job.objects.filter(dedupe_key=dedupe_key)
        if not dedupe_any_status:
            qs = qs.filter(status__in=["pending", "running"])
        if qs.exists():
            return None
    return Job.objects.create(type=job_type, payload=payload or {}, queue=queue or _QUEUES.get(job_type, "system"),
                              priority=priority, run_at=run_at or timezone.now(), dedupe_key=dedupe_key,
                              business_id=business_id, max_attempts=max_attempts)


def claim(worker: str, queue: str) -> Job | None:
    now = timezone.now()
    with transaction.atomic():
        qs = Job.objects.filter(status="pending", queue=queue, run_at__lte=now).order_by("priority", "run_at", "id")
        if connection.vendor == "mysql":
            qs = qs.select_for_update(skip_locked=True)
        job = qs.first()
        if not job:
            return None
        job.status, job.locked_by, job.locked_at = "running", worker, now
        job.attempts += 1
        job.save(update_fields=["status", "locked_by", "locked_at", "attempts"])
        return job


def recover_stuck() -> int:
    """Worker qulaganda qotib qolgan vazifalarni navbatga qaytaradi."""
    now = timezone.now()
    n = 0
    for q, key, default in (("media", "jobs.media_lock_timeout_min", 60),):
        pass
    std = int(get_setting("jobs.lock_timeout_min", 10))
    med = int(get_setting("jobs.media_lock_timeout_min", 60))
    for job in Job.objects.filter(status="running"):
        limit = med if job.queue == "media" else std
        if job.locked_at and job.locked_at < now - timedelta(minutes=limit):
            job.status, job.locked_by, job.locked_at = "pending", "", None
            job.last_error = (job.last_error + "\n[qayta navbatga qaytarildi: qotib qolgan]").strip()
            job.save(update_fields=["status", "locked_by", "locked_at", "last_error"])
            n += 1
    return n


def recover_orphans(worker_name: str) -> int:
    """Ishchi qayta ishga tushganda: shu kompyuterdagi ESKI jarayonlar qoldirgan 'running' vazifalarni darrov qaytaradi."""
    from datetime import timedelta as _td

    from .models import WorkerHeartbeat
    host, _, pid = worker_name.partition(":")
    n = 0
    fresh = timezone.now() - _td(seconds=45)
    alive = {h.name for h in WorkerHeartbeat.objects.filter(beat_at__gte=fresh)}
    for job in Job.objects.filter(status="running", locked_by__startswith=f"{host}:"):
        owner = job.locked_by.split("/", 1)[0]
        if owner == worker_name or owner in alive:
            continue
        job.status, job.locked_by, job.locked_at = "pending", "", None
        job.save(update_fields=["status", "locked_by", "locked_at"])
        n += 1
    return n


def execute(job: Job) -> None:
    """Bitta vazifani bajaradi va natijani qayd etadi (xato siyosati bilan)."""
    from apps.connections.base import PlatformError
    from apps.core.notify import notify
    handler = get_handler(job.type)
    if handler is None:
        _finish(job, "failed", f"Handler topilmadi: {job.type}")
        return
    ctx = JobContext(job, job.payload)
    try:
        result = handler(ctx)
        job.refresh_from_db(fields=["status"])
        if job.status == "cancelled":
            return
        job.result = result if isinstance(result, (dict, list)) else ({"value": result} if result is not None else None)
        job.progress = 100
        _finish(job, "done")
    except Exception as e:  # noqa: BLE001
        from apps.ai_router.router import AIUnavailable
        from apps.providers.base import NoProviderAvailable
        if isinstance(e, NoProviderAvailable):
            job.attempts = max(0, job.attempts - 1)  # urinish sanalmaydi
            _reschedule(job, e.retry_at or timezone.now() + timedelta(hours=1), f"provayder yo'q: {e}")
            return
        retryable = getattr(e, "retryable", True) if isinstance(e, PlatformError) else True
        if isinstance(e, AIUnavailable):
            retryable = True
        msg = f"{type(e).__name__}: {e}"
        log.exception("job %s xato", job)
        if retryable and job.attempts < job.max_attempts:
            wait = BACKOFF_MIN[min(job.attempts - 1, len(BACKOFF_MIN) - 1)]
            ra = getattr(e, "retry_after", None)
            _reschedule(job, timezone.now() + timedelta(minutes=wait, seconds=ra or 0), msg)
        else:
            _finish(job, "failed", msg)
            notify("job.failed", f"Vazifa xatosi: {job.type}", msg[:400], severity="warn",
                   business_id=job.business_id, dedupe_key=f"jobfail:{job.type}:{job.business_id}")


def _reschedule(job: Job, when, msg: str) -> None:
    job.status, job.run_at, job.locked_by, job.locked_at = "pending", when, "", None
    job.last_error = msg[:4000]
    job.save(update_fields=["status", "run_at", "locked_by", "locked_at", "last_error", "attempts"])


def _finish(job: Job, status: str, err: str = "") -> None:
    job.status, job.finished_at, job.locked_by = status, timezone.now(), ""
    if err:
        job.last_error = err[:4000]
    job.save()
