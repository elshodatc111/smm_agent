from django.core.management.base import BaseCommand

from apps.accounts.models import Role
from apps.accounts.permissions_registry import PRESET_ROLES, codes
from apps.accounts.services import set_role_permissions
from apps.businesses.services import ensure_templates


class Command(BaseCommand):
    help = "Boshlang'ich rollar, andozalar va ruxsatlarni yuklaydi (qayta ishga tushirsa xavfsiz)."

    def handle(self, *a, **o):
        admin, _ = Role.objects.get_or_create(name="Admin", defaults={"is_system": True, "description": "To'liq huquq"})
        Role.objects.get_or_create(name="Mijoz (faqat bot)", defaults={"is_system": True, "description": "Veb-kirish yo'q; faqat Telegram bot"})
        for name, spec in PRESET_ROLES.items():
            role, created = Role.objects.get_or_create(name=name, defaults={"is_system": False})
            if created:  # admin sozlagan ruxsatlarni qayta yozmaymiz
                set_role_permissions(role, codes(spec))
        ensure_templates()
        self.stdout.write(self.style.SUCCESS("Rollar va andozalar tayyor."))
