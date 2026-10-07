"""Brauzer (Playwright) tutun-testi: kirish, barcha menyu sahifalari, post formasi (matn formatlash, fayl, kesish, saqlash).
Ishlatish:  python tools/e2e_smoke.py http://127.0.0.1:8000 admin PAROL [--mobile]
Talab: pip install playwright && playwright install chromium. Xato bo'lsa chiqish kodi 1.
Diqqat: «Post formasi» qadami tanlangan biznesga bitta qoralama post qo'shadi."""
from __future__ import annotations

import struct
import sys
import tempfile
import zlib
from pathlib import Path

from playwright.sync_api import sync_playwright


def png(path: Path, w=1200, h=900):
    raw = b"".join(b"\x00" + bytes([40, 120, 200]) * w for _ in range(h))
    def ch(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))


def main() -> int:
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    base, user, pwd = (a + ["http://127.0.0.1:8000", "admin", ""])[:3] if len(a) < 3 else a[:3]
    mobile = "--mobile" in sys.argv
    errs: list[str] = []
    with sync_playwright() as p, tempfile.TemporaryDirectory() as td:
        img = Path(td) / "test.png"
        png(img)
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900}, has_touch=mobile)
        pg = ctx.new_page()
        pg.on("console", lambda m: errs.append(f"{pg.url}: {m.text}") if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(f"{pg.url}: PAGEERR {e}"))
        pg.goto(base + "/app/")
        pg.wait_for_selector("input[name=username]")
        pg.fill("input[name=username]", user)
        pg.fill("input[name=password]", pwd)
        pg.click("button[type=submit]")
        pg.wait_for_selector("header", timeout=15000)
        sess = pg.evaluate("fetch('/api/v1/session/').then(r=>r.json())")
        biz = sess.get("businesses") or []
        if biz:
            pg.evaluate("(id)=>{const c=document.cookie.match(/csrftoken=([^;]+)/)[1];return fetch('/biznes-tanlash/',{method:'POST',headers:{'X-CSRFToken':c},body:new URLSearchParams({business:id})})}", biz[0]["id"])
        urls = [i["url"] for g in sess["nav"] for i in g["items"]] + ["/kalendar/yangi/", "/kalendar/yangi/telegram/", "/sozlamalar/?tab=brend", "/sozlamalar/?tab=xizmatlar"]
        for u in dict.fromkeys(urls):
            n = len(errs)
            pg.goto(base + "/app" + u)
            pg.wait_for_load_state("networkidle")
            pg.wait_for_selector("main", timeout=10000)
            if "Server xatosi" in pg.inner_text("main"):
                errs.append(f"{u}: sahifa 500 xato ko'rsatdi")
            print(("XATO " if len(errs) > n else "ok   ") + u)
        # post formasi
        pg.goto(base + "/app/kalendar/yangi/telegram/")
        pg.wait_for_selector("#id_text")
        pg.fill("#id_text", "Salom dunyo")
        pg.evaluate("()=>{const t=document.getElementById('id_text');t.focus();t.setSelectionRange(0,5)}")
        pg.click("button[title^='Qalin']")
        assert pg.input_value("#id_text") == "<b>Salom</b> dunyo", "qalin teg qo'yilmadi"
        pg.set_input_files("input[type=file]", str(img))
        pg.wait_for_selector("button[title='Kesish']")
        pg.click("button[title='Kesish']")
        pg.click("button:has-text('Tayyor')")
        pg.wait_for_selector("text=kesilgan.jpg", timeout=8000)
        pg.click("button[type=submit]:has-text('Saqlash')")
        pg.wait_for_url("**/kalendar/*/", timeout=15000)
        print("ok   post formasi (formatlash, fayl, kesish, saqlash)")
        br.close()
    for e in errs:
        print("XATO:", e)
    print("TAYYOR" if not errs else f"{len(errs)} ta xato")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
