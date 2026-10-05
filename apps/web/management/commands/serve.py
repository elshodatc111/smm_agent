from django.core.management.base import BaseCommand

from config.env import env


class Command(BaseCommand):
    help = "Veb-serverni Waitress bilan ishga tushiradi (Windows uchun mos)."

    def handle(self, *a, **o):
        from waitress import serve
        from config.wsgi import application
        host, port = env("HOST", "0.0.0.0"), int(env("PORT", "8000"))
        self.stdout.write(f"SMM Platforma: http://{host}:{port}  (to'xtatish: Ctrl+C yoki stop.bat)")
        serve(application, host=host, port=port, threads=int(env("WEB_THREADS", "8")), max_request_body_size=2 * 1024 ** 3,
              channel_timeout=300)
