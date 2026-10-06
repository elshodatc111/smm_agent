"""Server javob bergunicha kutadi (restart.bat uchun). --open: tayyor bo'lsa brauzerda ochadi."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.env import env, load_env  # noqa: E402

load_env()
PORT = env("PORT", "8000")


def alive() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1/health/", timeout=4) as r:
            return bool(json.loads(r.read()).get("ok"))
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    limit = float(next((a.split("=")[1] for a in sys.argv if a.startswith("--timeout=")), "120"))
    t0 = time.time()
    while time.time() - t0 < limit:
        if alive():
            print(f"Server tayyor ({time.time() - t0:.0f} soniya).")
            if "--open" in sys.argv:
                webbrowser.open(f"http://127.0.0.1:{PORT}/")
            return 0
        time.sleep(2)
    return 1


if __name__ == "__main__":
    sys.exit(main())
