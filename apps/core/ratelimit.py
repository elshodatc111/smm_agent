"""Oddiy, jarayon ichidagi tezlik cheklovchi: min interval + tasodifiy tebranish (jitter)."""
import random
import threading
import time

_lock = threading.Lock()
_last: dict[str, float] = {}
SLEEP = time.sleep  # testlarda almashtiriladi


def throttle(key: str, min_interval: float, jitter: float = 0.0) -> float:
    """Oxirgi chaqiruvdan beri min_interval(+jitter) o'tmagan bo'lsa kutadi. Kutilgan soniyani qaytaradi."""
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _last.get(key, 0.0) + min_interval + random.uniform(0, jitter) - now)
        _last[key] = now + wait
    if wait > 0:
        SLEEP(wait)
    return wait
