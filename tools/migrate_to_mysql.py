"""SQLite -> MySQL ko'chirish ustasi. Xavfsiz: avval zaxira oladi, xato bo'lsa .env ni o'zgartirmaydi.
Parollar ekranga chiqarilmaydi. Qayta ishga tushirsa bo'ladi."""
from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
EXCLUDE = ["contenttypes", "auth.permission", "sessions"]


def ask(q, default="", secret=False):
    s = f"{q}" + (f" [{default}]" if default and not secret else "") + ": "
    v = (getpass.getpass(s) if secret else input(s)).strip()
    return v or default


def read_env():
    d = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def write_env(updates):
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    seen = set()
    out = []
    for line in lines:
        k = line.split("=", 1)[0].strip()
        if "=" in line and not line.strip().startswith("#") and k in updates:
            out.append(f"{k}={updates[k]}")
            seen.add(k)
        else:
            out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def manage(args, env_over, capture=False):
    env = dict(os.environ)
    env.update(env_over)
    cmd = [sys.executable, str(ROOT / "manage.py"), *args]
    if capture:
        return subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    return subprocess.run(cmd, cwd=ROOT, env=env)


COUNT_CODE = (
    "import json\n"
    "from django.apps import apps\n"
    "r={}\n"
    "for m in apps.get_models():\n"
    "    if m._meta.app_label in ('contenttypes','sessions','admin'): continue\n"
    "    if m._meta.label=='auth.Permission': continue\n"
    "    try: r[m._meta.label]=m.objects.count()\n"
    "    except Exception as e: r[m._meta.label]=-1\n"
    "print('COUNTS='+json.dumps(r))\n"
)


def counts(env_over):
    p = manage(["shell", "-c", COUNT_CODE], env_over, capture=True)
    for line in p.stdout.splitlines():
        if line.startswith("COUNTS="):
            return json.loads(line[7:])
    return None


def main():
    print("=" * 60)
    print("  SQLite  ->  MySQL ko'chirish")
    print("=" * 60)
    env = read_env()
    if env.get("DB_ENGINE", "mysql") != "sqlite":
        print("Tizim allaqachon MySQL da ishlayapti (.env: DB_ENGINE=mysql). Ko'chirish kerak emas.")
        return 0
    dbf = ROOT / "db.sqlite3"
    if not dbf.exists():
        print("db.sqlite3 topilmadi — ko'chiradigan ma'lumot yo'q. Shunchaki .env da DB_ENGINE=mysql qiling.")
        return 1
    try:
        import pymysql
    except ImportError:
        print("pymysql o'rnatilmagan: run.bat ni bir marta ishga tushiring (kutubxonalar o'rnatiladi).")
        return 1

    print("\n--- 1/6. MySQL ulanish ma'lumotlari ---")
    host = ask("MySQL manzili", "127.0.0.1")
    port = int(ask("MySQL porti", "3306"))
    name = ask("Yangi baza nomi", "smm_platform")
    user = ask("Baza foydalanuvchisi (yangi)", "smm")
    pw = ask("Baza paroli (yangi, o'zingiz o'ylab toping)", secret=True)
    if len(pw) < 8:
        print("Parol kamida 8 belgi bo'lsin.")
        return 1
    root_pw = ask("MySQL 'root' paroli (o'rnatishda kiritgansiz)", secret=True)
    try:
        c = pymysql.connect(host=host, port=port, user="root", password=root_pw, connect_timeout=8)
    except Exception as e:  # noqa: BLE001
        print(f"MySQL ga ulanib bo'lmadi: {str(e)[:200]}")
        print("MySQL o'rnatilganmi? services.msc -> MySQL80 -> Start. Yo'riqnoma: docs\\setup\\11-mysql-otish.md")
        return 1
    with c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s", (name,))
        existing = cur.fetchone()[0]
    if existing:
        print(f"Diqqat: '{name}' bazasida {existing} ta jadval bor (oldingi urinishdan qolgan bo'lishi mumkin).")
        if input("Bazani TOZALAB qaytadan boshlaymizmi? [y/N]: ").strip().lower() != "y":
            return 1
        with c.cursor() as cur:
            cur.execute(f"DROP DATABASE `{name}`")
    with c.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        for h in ("localhost", "127.0.0.1"):
            cur.execute(f"CREATE USER IF NOT EXISTS '{user}'@'{h}' IDENTIFIED BY %s", (pw,))
            cur.execute(f"ALTER USER '{user}'@'{h}' IDENTIFIED BY %s", (pw,))
            cur.execute(f"GRANT ALL ON `{name}`.* TO '{user}'@'{h}'")
        cur.execute("FLUSH PRIVILEGES")
    c.commit(); c.close()
    print("Baza va foydalanuvchi tayyor.")

    my = {"DB_ENGINE": "mysql", "DB_HOST": host, "DB_PORT": str(port), "DB_NAME": name, "DB_USER": user, "DB_PASSWORD": pw}
    lite = {"DB_ENGINE": "sqlite"}

    print("\n--- 2/6. SQLite zaxirasi ---")
    bdir = ROOT / "backups"
    bdir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bk = bdir / f"sqlite-before-mysql-{stamp}.sqlite3"
    try:
        import sqlite3
        src = sqlite3.connect(str(dbf)); dst = sqlite3.connect(str(bk))
        src.backup(dst); dst.close(); src.close()
    except Exception:  # noqa: BLE001
        shutil.copy2(dbf, bk)
    shutil.copy2(ENV, ROOT / f".env.sqlite-{stamp}.bak")
    print(f"Zaxira: backups\\{bk.name} (va .env nusxasi)")

    print("\n--- 3/6. SQLite dagi ma'lumotlarni o'qish ---")
    manage(["migrate", "--noinput"], lite)
    dump = bdir / f"dump-{stamp}.json"
    args = ["dumpdata", "--natural-foreign", "--indent", "0", "-o", str(dump)]
    for e in EXCLUDE:
        args += ["--exclude", e]
    r = manage(args, lite)
    if r.returncode != 0 or not dump.exists():
        print("SQLite dan o'qib bo'lmadi. .env o'zgartirilmadi.")
        return 1
    print(f"Ma'lumotlar o'qildi ({dump.stat().st_size // 1024} KB).")

    print("\n--- 4/6. MySQL da jadvallar yaratish ---")
    if manage(["migrate", "--noinput"], my).returncode != 0:
        print("MySQL da jadval yaratib bo'lmadi. .env o'zgartirilmadi.")
        return 1

    print("\n--- 5/6. Ma'lumotlarni MySQL ga yuklash ---")
    if manage(["loaddata", str(dump)], my).returncode != 0:
        print("Yuklashda xato. .env o'zgartirilmadi — tizim SQLite da ishlashda davom etadi. Xabarni menga yuboring.")
        return 1

    print("\n--- 6/6. Tekshirish ---")
    a, b = counts(lite), counts(my)
    bad = []
    if a and b:
        for k, v in a.items():
            if v >= 0 and b.get(k, -1) != v:
                bad.append((k, v, b.get(k)))
    if bad:
        print("Qatorlar soni mos kelmadi:")
        for k, v, w in bad[:15]:
            print(f"   {k}: SQLite={v}  MySQL={w}")
        if input("Baribir MySQL ga o'tamizmi? [y/N]: ").strip().lower() != "y":
            print(".env o'zgartirilmadi.")
            return 1
    else:
        tot = sum(v for v in (a or {}).values() if v > 0)
        print(f"Hammasi mos: jami {tot} ta yozuv ko'chirildi.")

    write_env(my)
    print("\n.env yangilandi: endi tizim MySQL da ishlaydi.")
    print(f"Orqaga qaytish: .env.sqlite-{stamp}.bak ni .env ga nusxalang (SQLite ma'lumotlari db.sqlite3 da saqlangan).")
    print("Endi run.bat ni ishga tushiring (autostart yoqilgan bo'lsa — kompyuterni qayta yoqing).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nBekor qilindi. .env o'zgartirilmadi.")
        sys.exit(1)
