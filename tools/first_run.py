"""Birinchi sozlash ustasi: .env yaratadi, bazani tayyorlaydi, admin yaratadi. Qayta ishga tushirsa xavfsiz."""
from __future__ import annotations

import getpass
import secrets
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"


def ask(q, default="", secret=False):
    s = f"{q}" + (f" [{default}]" if default and not secret else "") + ": "
    v = (getpass.getpass(s) if secret else input(s)).strip()
    return v or default


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def py(*args):
    return subprocess.call([sys.executable, str(ROOT / "manage.py"), *args], cwd=ROOT)


def make_env():
    print("\n=== 1/4. Asosiy sozlamalar ===")
    try:
        from cryptography.fernet import Fernet
        fkey = Fernet.generate_key().decode()
    except ImportError:
        print("cryptography o'rnatilmagan — avval: pip install -r requirements.txt")
        sys.exit(1)
    mode = ask("Ma'lumotlar bazasi: 1 = MySQL (tavsiya), 2 = SQLite (faqat sinov)", "1")
    cfg = {"SECRET_KEY": secrets.token_urlsafe(50), "FERNET_KEYS": fkey, "HOST": "0.0.0.0", "PORT": "8000", "ALLOWED_HOSTS": "*", "DEBUG": "0", "USE_FAKES": "0"}
    if mode == "2":
        cfg["DB_ENGINE"] = "sqlite"
    else:
        cfg.update(DB_ENGINE="mysql", DB_HOST=ask("MySQL manzili", "127.0.0.1"), DB_PORT=ask("MySQL porti", "3306"),
                   DB_NAME=ask("Baza nomi", "smm_platform"), DB_USER=ask("Baza foydalanuvchisi", "smm"))
        cfg["DB_PASSWORD"] = ask("Baza paroli (yangi, o'zingiz o'ylab toping)", secret=True)
        root_pw = ask("MySQL 'root' paroli (bazani avtomatik yaratish uchun; bo'sh = bazani o'zim yaratganman)", secret=True)
        if root_pw:
            try:
                import pymysql
                c = pymysql.connect(host=cfg["DB_HOST"], port=int(cfg["DB_PORT"]), user="root", password=root_pw)
                with c.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{cfg['DB_NAME']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                    cur.execute(f"CREATE USER IF NOT EXISTS '{cfg['DB_USER']}'@'localhost' IDENTIFIED BY %s", (cfg["DB_PASSWORD"],))
                    cur.execute(f"GRANT ALL ON `{cfg['DB_NAME']}`.* TO '{cfg['DB_USER']}'@'localhost'")
                    cur.execute("FLUSH PRIVILEGES")
                c.commit()
                print("  Baza va foydalanuvchi yaratildi.")
            except Exception as e:  # noqa: BLE001
                print(f"  ! Bazani yaratib bo'lmadi: {e}\n  Yo'riqnomadagi MySQL bo'limi bo'yicha qo'lda yarating.")
    ip = lan_ip()
    cfg["PUBLIC_BASE_URL"] = ask("Tizim manzili (LAN dagi boshqa kompyuterlar shu orqali kiradi)", f"http://{ip}:8000")
    ENV.write_text("# Avtomatik yaratildi. Bu faylni hech kimga yubormang.\n" + "\n".join(f"{k}={v}" for k, v in cfg.items()) + "\n", encoding="utf-8")
    print("\n" + "!" * 70)
    print("MUHIM: quyidagi FERNET kalitni alohida joyga (flesh/parol menejeri) nusxalang.")
    print("Bu kalit yo'qolsa, bazadagi barcha ulanish tokenlari va API kalitlari ochilmay qoladi:")
    print("   " + fkey)
    print("!" * 70 + "\n")


def db_reachable():
    """.env dagi bazaga ulanib ko'radi; (ok, xabar)."""
    env = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    if env.get("DB_ENGINE") == "sqlite":
        return True, ""
    try:
        import pymysql
        pymysql.connect(host=env.get("DB_HOST", "127.0.0.1"), port=int(env.get("DB_PORT", "3306")), user=env.get("DB_USER", ""),
                        password=env.get("DB_PASSWORD", ""), database=env.get("DB_NAME", ""), connect_timeout=5).close()
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:200]


def main():
    first = not ENV.exists()
    if first:
        make_env()
    else:
        print(".env mavjud — o'tkazib yuborildi.")
    ok, err = db_reachable()
    if not ok:
        print("\n[!] MySQL bazasiga ulanib bo'lmadi:", err)
        print("    Sabablari: MySQL o'rnatilmagan/ishlamayapti (services.msc -> MySQL80 -> Start), parol yoki baza nomi noto'g'ri.")
        print("    MySQL o'rnatish: docs\\setup\\01-mysql.md")
        if input("    Hozircha SQLite (sinov rejimi) bilan davom etamizmi? [y/N]: ").strip().lower() == "y":
            txt = ENV.read_text(encoding="utf-8").replace("DB_ENGINE=mysql", "DB_ENGINE=sqlite")
            ENV.write_text(txt, encoding="utf-8")
            print("    .env da DB_ENGINE=sqlite qilindi. MySQL tayyor bo'lgach DB_ENGINE=mysql qilib qaytaring.")
        else:
            print("    MySQL ni tayyorlang va run.bat ni qayta ishga tushiring (.env saqlangan).")
            sys.exit(1)
    print("=== 2/4. Baza jadvallari ===")
    if py("migrate", "--noinput") != 0:
        print("Baza bilan muammo: .env dagi DB_* sozlamalarini va MySQL ishlayotganini tekshiring.")
        sys.exit(1)
    py("bootstrap")
    print("=== 3/4. Administrator ===")
    if (first or "--admin" in sys.argv) and input("Administrator yaratamizmi/parolini yangilaymizmi? [Y/n]: ").strip().lower() != "n":
        py("createadmin")
    print("=== 4/4. Tekshiruv ===")
    py("doctor")
    print("\nTayyor. Endi run.bat ni ishga tushiring, brauzerda tizim manzilini oching.")


if __name__ == "__main__":
    main()
