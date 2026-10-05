import shutil
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Muhit tekshiruvi: Python, baza, kalitlar, ffmpeg, papkalar, sozlamalar."

    def handle(self, *a, **o):
        ok = True

        def line(label, good, hint=""):
            nonlocal ok
            ok &= bool(good)
            self.stdout.write(("  [OK]   " if good else "  [XATO] ") + label + ("" if good else f"  -> {hint}"))
        line(f"Python {sys.version.split()[0]}", sys.version_info >= (3, 11), "Python 3.12 o'rnating")
        try:
            connection.ensure_connection()
            line(f"Baza ({connection.vendor}) ulandi", True)
        except Exception as e:  # noqa: BLE001
            line("Baza ulanishi", False, str(e)[:120])
        line("FERNET_KEYS .env da", bool(settings.FERNET_KEYS), "run.bat birinchi sozlash ustasini ishga tushiring")
        line("SECRET_KEY o'zgartirilgan", settings.SECRET_KEY != "dev-insecure-key-change-me", ".env ni tekshiring")
        line("ffmpeg", shutil.which("ffmpeg"), "ffmpeg o'rnating va PATH ga qo'shing (media tahlil uchun)")
        line("ffprobe", shutil.which("ffprobe"), "ffmpeg bilan birga keladi")
        line("mysqldump (zaxira)", __import__("apps.health.jobs", fromlist=["x"]).find_dump_tool() or "sqlite" in settings.DATABASES["default"]["ENGINE"],
             "MySQL bin papkasini PATH ga qo'shing")
        for lib, why in (("faster_whisper", "lokal STT (ixtiyoriy)"), ("telethon", "Telegram statistika akkaunti (ixtiyoriy)"),
                         ("cv2", "yuz aniqlash (ixtiyoriy)")):
            try:
                __import__(lib)
                line(f"{lib} o'rnatilgan", True)
            except ImportError:
                self.stdout.write(f"  [--]    {lib} o'rnatilmagan ({why})")
        for d in ("media_store", "media_tmp", "logs", "backups"):
            (settings.BASE_DIR / d).mkdir(exist_ok=True)
        from apps.core.settings_store import get_setting
        for key, label in (("worker.cloudflare_url", "Cloudflare Worker manzili"), ("meta.app_id", "Meta App ID"), ("google.client_id", "Google Client ID")):
            self.stdout.write(f"  [{'OK' if get_setting(key) else '--'}]   {label}: {'kiritilgan' if get_setting(key) else 'hali kiritilmagan (Sozlamalar)'}")
        self.stdout.write(self.style.SUCCESS("Hammasi joyida." if ok else "Muammolar bor — yuqoridagi tavsiyalarga qarang."))
