from django.core.management.base import BaseCommand

from apps.health.jobs import run_backup


class Command(BaseCommand):
    help = "Bazaning zaxira nusxasini oladi (backups/ papkasiga)."

    def handle(self, *a, **o):
        r = run_backup()
        if r.ok:
            self.stdout.write(self.style.SUCCESS(f"Tayyor: {r.path} ({r.size // 1024} KB)"))
            self.stdout.write(self.style.WARNING("MUHIM: .env dagi FERNET_KEYS ni boshqa xavfsiz joyga (parol menejeri) ham nusxalang. "
                                                  "Usiz shifrlangan tokenlarni tiklab bo'lmaydi."))
        else:
            self.stderr.write("Zaxira xatosi: " + r.note)
