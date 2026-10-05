from datetime import timedelta

from django.utils import timezone

from apps.jobs import queue as q
from apps.jobs.models import Job
from apps.connections.base import TransientError, AuthError


def test_enqueue_dedupe_and_claim_order():
    a = q.enqueue("t", {}, queue="system", dedupe_key="k")
    assert q.enqueue("t", {}, queue="system", dedupe_key="k") is None
    b = q.enqueue("t2", {}, queue="system", priority=1)
    first = q.claim("w", "system")
    assert first.pk == b.pk and first.attempts == 1
    assert q.claim("w", "collect") is None


def test_future_job_not_claimed():
    q.enqueue("t", {}, queue="system", run_at=timezone.now() + timedelta(hours=1))
    assert q.claim("w", "system") is None


def test_retry_backoff_then_fail():
    calls = []

    @q.register_handler("flaky", "system")
    def h(ctx):
        calls.append(1)
        raise TransientError("net")
    j = q.enqueue("flaky", {}, queue="system", max_attempts=2)
    job = q.claim("w", "system")
    q.execute(job)
    job.refresh_from_db()
    assert job.status == "pending" and job.run_at > timezone.now() + timedelta(seconds=30)
    Job.objects.filter(pk=job.pk).update(run_at=timezone.now())
    job = q.claim("w", "system")
    q.execute(job)
    job.refresh_from_db()
    assert job.status == "failed" and len(calls) == 2


def test_non_retryable_fails_fast(admin):
    @q.register_handler("auth", "system")
    def h(ctx):
        raise AuthError("bad")
    q.enqueue("auth", {}, queue="system")
    job = q.claim("w", "system")
    q.execute(job)
    job.refresh_from_db()
    assert job.status == "failed"


def test_stuck_job_recovered():
    j = q.enqueue("t", {}, queue="system")
    job = q.claim("w", "system")
    Job.objects.filter(pk=job.pk).update(locked_at=timezone.now() - timedelta(minutes=30))
    assert q.recover_stuck() == 1
    job.refresh_from_db()
    assert job.status == "pending"


def test_no_provider_reschedules_without_attempt():
    from apps.providers.base import NoProviderAvailable

    @q.register_handler("noprov", "system")
    def h(ctx):
        raise NoProviderAvailable("x", timezone.now() + timedelta(hours=5))
    q.enqueue("noprov", {}, queue="system")
    job = q.claim("w", "system")
    q.execute(job)
    job.refresh_from_db()
    assert job.status == "pending" and job.attempts == 0 and job.run_at > timezone.now() + timedelta(hours=4)
