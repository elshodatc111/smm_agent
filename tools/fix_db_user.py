"""MySQL ulanish xatosini (Access denied) tuzatadi: 'smm' foydalanuvchisini yaratadi/yangilaydi va .env ni yangilaydi.
Parol avtomatik yaratiladi va ekranga chiqarilmaydi. root paroli faqat bir marta so'raladi va saqlanmaydi."""
from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"


def read_env():
    d = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def write_env(updates):
    out, seen = [], set()
    for line in ENV.read_text(encoding="utf-8").splitlines():
        k = line.split("=", 1)[0].strip()
        if "=" in line and not line.strip().startswith("#") and k in updates:
            out.append(f"{k}={updates[k]}")
            seen.add(k)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in updates.items() if k not in seen]
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def main():
    import pymysql
    env = read_env()
    host, port = env.get("DB_HOST", "127.0.0.1"), int(env.get("DB_PORT", "3306"))
    name, user = env.get("DB_NAME", "smm_platform"), "smm"
    print("MySQL 'root' parolini kiriting (MySQL o'rnatishda qo'ygan parolingiz). U saqlanmaydi.")
    rp = getpass.getpass("root paroli: ")
    try:
        c = pymysql.connect(host=host, port=port, user="root", password=rp, connect_timeout=8)
    except Exception as e:  # noqa: BLE001
        print(f"\nroot bilan kirib bo'lmadi: {str(e)[:150]}")
        print("Parol noto'g'ri bo'lsa — docs\\setup\\11-mysql-otish.md dagi «root parolini tiklash» bo'limiga qarang yoki menga yozing.")
        return 1
    pw = secrets.token_urlsafe(18)
    with c.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        for h in ("localhost", "127.0.0.1"):
            cur.execute(f"CREATE USER IF NOT EXISTS '{user}'@'{h}' IDENTIFIED BY %s", (pw,))
            cur.execute(f"ALTER USER '{user}'@'{h}' IDENTIFIED BY %s", (pw,))
            cur.execute(f"GRANT ALL ON `{name}`.* TO '{user}'@'{h}'")
        cur.execute("FLUSH PRIVILEGES")
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s", (name,))
        n = cur.fetchone()[0]
    c.commit(); c.close()
    try:
        pymysql.connect(host=host, port=port, user=user, password=pw, database=name, connect_timeout=8).close()
    except Exception as e:  # noqa: BLE001
        print(f"Yangi foydalanuvchi bilan ulanib bo'lmadi: {str(e)[:150]}")
        return 1
    write_env({"DB_USER": user, "DB_PASSWORD": pw})
    print(f"\nTayyor: '{name}' bazasida {n} ta jadval bor, foydalanuvchi '{user}' yaratildi, .env yangilandi.")
    if n == 0:
        print("Diqqat: baza bo'sh. Ma'lumotlaringiz shu bazada bo'lishi kerak edi — avval mysql_otish.bat ni ishga tushirgan bo'lsangiz, menga xabar bering.")
    print("Endi stop.bat, so'ng run.bat ni ishga tushiring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
