"""Worker jarayoni: navbatlar bo'yicha oqimlar + scheduler + heartbeat + bot (Celery/Redis o'rniga)."""
from __future__ import annotations

import logging
import os
import socket
import threading
import time

from django.db import close_old_connections
from django.utils import timezone

from apps.core.settings_store import get_setting

from . import queue as q
from .models import WorkerHeartbeat

log = logging.getLogger(__name__)
POLL = 2.5


class Backoff:
    """Takroriy xatoda kutishni 5s dan 5 daqiqagacha oshiradi va logga bitta qisqa qator yozadi
    (to'liq traceback faqat birinchi marta va har 50-takrorda) — baza vaqtincha o'chganda log faylni to'ldirib yubormaslik uchun."""

    def __init__(self, base: float = 5.0, cap: float = 300.0):
        self.base, self.cap, self.n = base, cap, 0

    def fail(self, what: str, exc: BaseException) -> float:
        self.n += 1
        if self.n == 1 or self.n % 50 == 0:
            log.error("%s: %s (takror: %s)", what, exc, self.n, exc_info=(self.n == 1))
        else:
            log.warning("%s: %s (takror: %s)", what, str(exc)[:160], self.n)
        return min(self.cap, self.base * (2 ** min(self.n - 1, 6)))

    def ok(self) -> None:
        if self.n:
            log.info("Xato bartaraf bo'ldi (%s urinishdan keyin)", self.n)
        self.n = 0


def load_handlers() -> None:
    import importlib
    for mod in ("metrics", "content", "studio", "media_analysis", "reports", "tgbot", "health", "connections", "goals"):
        try:
            importlib.import_module(f"apps.{mod}.jobs")
        except ModuleNotFoundError as e:
            if e.name != f"apps.{mod}.jobs":
                raise


class Worker:
    def __init__(self):
        self.name = f"{socket.gethostname()}:{os.getpid()}"
        self.stop = threading.Event()

    def _loop(self, queue: str, slot: int):
        close_old_connections()
        bo = Backoff()
        while not self.stop.is_set():
            try:
                job = q.claim(f"{self.name}/{queue}{slot}", queue)
                bo.ok()
                if job is None:
                    self.stop.wait(POLL)
                    continue
                q.execute(job)
            except Exception as e:  # noqa: BLE001
                self.stop.wait(bo.fail(f"worker oqimi ({queue}{slot})", e))
            finally:
                close_old_connections()

    def _housekeeping(self):
        from .scheduler import tick
        bo, wait = Backoff(10.0, 300.0), 10.0
        while not self.stop.is_set():
            try:
                WorkerHeartbeat.objects.update_or_create(name=self.name, defaults={"beat_at": timezone.now(), "info": {"pid": os.getpid()}})
                q.recover_stuck()
                tick()
                bo.ok()
                wait = 10.0
            except Exception as e:  # noqa: BLE001
                wait = bo.fail("scheduler", e)
            finally:
                close_old_connections()
            self.stop.wait(wait)

    def run_forever(self, with_bot: bool = True):
        load_handlers()
        try:
            n = q.recover_orphans(self.name)
            if n:
                log.info("Qotib qolgan %s ta vazifa qayta navbatga qaytarildi", n)
        except Exception:  # noqa: BLE001
            log.exception("orphan tiklash xatosi")
        sizes = get_setting("jobs.workers", {"publish": 2, "collect": 3, "ai": 2, "media": 1, "system": 1})
        threads = [threading.Thread(target=self._housekeeping, daemon=True, name="housekeeping")]
        for queue, n in sizes.items():
            for i in range(int(n)):
                threads.append(threading.Thread(target=self._loop, args=(queue, i), daemon=True, name=f"{queue}{i}"))
        if with_bot:
            from apps.tgbot.bot import run_bot_loop
            threads.append(threading.Thread(target=run_bot_loop, args=(self.stop,), daemon=True, name="tgbot"))
            from apps.inbox.listener import run_inbox_loop
            threads.append(threading.Thread(target=run_inbox_loop, args=(self.stop,), daemon=True, name="inbox"))
            from apps.online.bot import run_online_loop
            threads.append(threading.Thread(target=run_online_loop, args=(self.stop,), daemon=True, name="online"))
        for t in threads:
            t.start()
        log.info("Worker ishga tushdi: %s oqim", len(threads))
        try:
            while not self.stop.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop.set()
