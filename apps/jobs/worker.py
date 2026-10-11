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


def load_handlers() -> None:
    import importlib
    for mod in ("metrics", "content", "studio", "media_analysis", "reports", "tgbot", "health", "connections", "goals", "facts"):
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
        while not self.stop.is_set():
            try:
                job = q.claim(f"{self.name}/{queue}{slot}", queue)
                if job is None:
                    self.stop.wait(POLL)
                    continue
                q.execute(job)
            except Exception:  # noqa: BLE001
                log.exception("worker oqimi xatosi")
                self.stop.wait(5)
            finally:
                close_old_connections()

    def _housekeeping(self):
        from .scheduler import tick
        while not self.stop.is_set():
            try:
                WorkerHeartbeat.objects.update_or_create(name=self.name, defaults={"beat_at": timezone.now(), "info": {"pid": os.getpid()}})
                q.recover_stuck()
                tick()
            except Exception:  # noqa: BLE001
                log.exception("scheduler xatosi")
            finally:
                close_old_connections()
            self.stop.wait(10)

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
        for t in threads:
            t.start()
        log.info("Worker ishga tushdi: %s oqim", len(threads))
        try:
            while not self.stop.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop.set()
