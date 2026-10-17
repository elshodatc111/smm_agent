from django.core.management.base import BaseCommand

from apps.accounts.models import Role
from apps.accounts.permissions_registry import ALL_CODES, LATE_MODULES, PRESET_ROLES, codes
from apps.accounts.services import set_role_permissions
from apps.businesses.services import ensure_templates


class Command(BaseCommand):
    help = "Boshlang'ich rollar, andozalar va ruxsatlarni yuklaydi (qayta ishga tushirsa xavfsiz)."

    def handle(self, *a, **o):
        self._purge_stale_codes()
        self._drop_removed_modules()
        from apps.jobs.models import Job
        Job.objects.filter(type__startswith="facts_").delete()   # olib tashlangan modul vazifalari
        admin, _ = Role.objects.get_or_create(name="Admin", defaults={"is_system": True, "description": "To'liq huquq"})
        Role.objects.get_or_create(name="Mijoz (faqat bot)", defaults={"is_system": True, "description": "Veb-kirish yo'q; faqat Telegram bot"})
        for name, spec in PRESET_ROLES.items():
            role, created = Role.objects.get_or_create(name=name, defaults={"is_system": False})
            if created:  # admin sozlagan ruxsatlarni qayta yozmaymiz
                set_role_permissions(role, codes(spec))
        self._grant_late_modules()
        ensure_templates()
        self.stdout.write(self.style.SUCCESS("Rollar va andozalar tayyor."))

    def _purge_stale_codes(self):
        """O'chirilgan modullar (havolalar, izohlar...) ruxsat kodlarini bazadan tozalaydi."""
        from apps.accounts.models import RolePermission, UserPermissionOverride
        RolePermission.objects.exclude(code__in=ALL_CODES).delete()
        UserPermissionOverride.objects.exclude(code__in=ALL_CODES).delete()

    def _drop_removed_modules(self):
        """Olib tashlangan «Onlayn kanal» moduli jadvallari, migratsiya yozuvlari va ruxsatlarini bazadan tozalaydi (qayta ishga tushirsa xavfsiz)."""
        from django.db import connection
        from django.db.migrations.recorder import MigrationRecorder
        tables = [t for t in connection.introspection.table_names() if t.startswith("online_")]
        if tables:
            q = connection.ops.quote_name
            with connection.cursor() as c:
                if connection.vendor == "mysql":
                    c.execute("SET FOREIGN_KEY_CHECKS=0")
                elif connection.vendor == "sqlite":
                    c.execute("PRAGMA foreign_keys=OFF")
                for t in tables:
                    c.execute(f"DROP TABLE IF EXISTS {q(t)}")
                if connection.vendor == "mysql":
                    c.execute("SET FOREIGN_KEY_CHECKS=1")
                elif connection.vendor == "sqlite":
                    c.execute("PRAGMA foreign_keys=ON")
            self.stdout.write(f"Olib tashlangan modul jadvallari tozalandi: {len(tables)} ta")
        MigrationRecorder.Migration.objects.filter(app="online").delete()
        from django.contrib.contenttypes.models import ContentType
        ContentType.objects.filter(app_label="online").delete()

    def _grant_late_modules(self):
        """Keyin qo'shilgan modullar (maqsadlar) uchun mavjud rollarga standart ruxsat — faqat bir marta."""
        from apps.accounts.models import RolePermission
        from apps.core.settings_store import get_setting, set_setting
        done = list(get_setting("rbac.late_granted", []) or [])
        changed = False
        for mod, spec in LATE_MODULES.items():
            if mod in done:
                continue
            for rname, acts in spec.items():
                role = Role.objects.filter(name=rname).first()
                if not role:
                    continue
                have = set(RolePermission.objects.filter(role=role).values_list("code", flat=True))
                set_role_permissions(role, have | codes({mod: acts}))
            done.append(mod)
            changed = True
        if changed:
            set_setting("rbac.late_granted", done)
