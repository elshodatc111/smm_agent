"""Baza tayyor bo'lguncha kutadi (MySQL xizmati kompyuter yoqilgach kech ochilishi mumkin). SQLite bo'lsa darrov chiqadi."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.env import env, load_env  # noqa: E402

load_env()
if env("DB_ENGINE", "mysql") == "sqlite":
    sys.exit(0)
import socket  # noqa: E402

host, port = env("DB_HOST", "127.0.0.1"), int(env("DB_PORT", "3306"))
t0 = time.time()
while time.time() - t0 < 300:
    try:
        socket.create_connection((host, port), timeout=3).close()
        print(f"Baza tayyor: {host}:{port}")
        sys.exit(0)
    except OSError:
        time.sleep(5)
print("Baza 5 daqiqa ichida ochilmadi — baribir davom etiladi.")
sys.exit(0)
