import getpass

from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Admin foydalanuvchi yaratadi (interaktiv yoki --username/--password)."

    def add_arguments(self, p):
        p.add_argument("--username")
        p.add_argument("--password")

    def handle(self, *a, **o):
        u = o["username"] or input("Admin login: ").strip()
        pw = o["password"] or getpass.getpass("Parol (kamida 8 belgi): ")
        if len(pw) < 8:
            self.stderr.write("Parol juda qisqa.")
            return
        user, created = User.objects.get_or_create(username=u, defaults={"is_admin": True, "is_staff": True, "is_superuser": True, "full_name": "Administrator"})
        user.is_admin = True
        user.set_password(pw)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin {'yaratildi' if created else 'yangilandi'}: {u}"))
