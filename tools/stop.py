import os
import sys
from pathlib import Path

import psutil

ROOT = str(Path(__file__).resolve().parent.parent).lower()
me = os.getpid()
n = 0
(Path(ROOT) / "logs").mkdir(exist_ok=True)
(Path(ROOT) / "logs" / "stop.flag").write_text("stop")   # avtomatik ishga tushish uni qayta yoqib yubormasligi uchun
for p in psutil.process_iter(["pid", "cmdline", "cwd"]):
    try:
        cmd = " ".join(p.info["cmdline"] or []).lower()
        if p.info["pid"] != me and (("supervisor.py" in cmd) or ("manage.py" in cmd and (" serve" in cmd or " worker" in cmd))) and ROOT in ((p.info["cwd"] or "").lower() + cmd):
            p.terminate()
            n += 1
    except (psutil.Error, OSError):
        pass
print(f"To'xtatildi: {n} ta jarayon.")
sys.exit(0)
