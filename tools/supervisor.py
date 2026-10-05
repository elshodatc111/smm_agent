"""Veb va worker jarayonlarini ishga tushiradi va kuzatadi: yiqilsa yoki osilib qolsa qayta ishga tushiradi (watchdog)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.env import env, load_env  # noqa: E402

load_env()
PORT = env("PORT", "8000")
LOG = ROOT / "logs"
LOG.mkdir(exist_ok=True)


def start(name):
    f = open(LOG / f"{name}.out.log", "ab")
    return subprocess.Popen([sys.executable, str(ROOT / "manage.py"), name], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)


def health():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1/health/", timeout=8) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def main():
    if health() is not None:     # allaqachon ishlayapti (masalan, avtomatik ishga tushish + qo'lda run.bat) — ikkinchi nusxa kerak emas
        print("SMM Platforma allaqachon ishlayapti, ikkinchi nusxa ishga tushirilmadi.")
        return
    (LOG / "stop.flag").unlink(missing_ok=True)
    procs = {"serve": start("serve"), "worker": start("worker")}
    print(f"SMM Platforma ishga tushdi: http://127.0.0.1:{PORT}  (to'xtatish: stop.bat)")
    (ROOT / "logs" / "supervisor.pid").write_text(str(__import__("os").getpid()))
    bad_beats, started = 0, time.time()
    try:
        while True:
            time.sleep(15)
            for name, p in list(procs.items()):
                if p.poll() is not None:
                    print(f"{name} to'xtagan (kod {p.returncode}), qayta ishga tushirilmoqda…")
                    procs[name] = start(name)
            if time.time() - started > 90:
                h = health()
                if h is None:
                    procs["serve"].terminate()
                elif not h.get("worker_alive"):
                    bad_beats += 1
                    if bad_beats >= 4:    # ~1 daqiqa heartbeat yo'q
                        procs["worker"].terminate()
                        bad_beats = 0
                else:
                    bad_beats = 0
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs.values():
            p.terminate()


if __name__ == "__main__":
    main()
