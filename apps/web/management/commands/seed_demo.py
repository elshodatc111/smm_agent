from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Role, User, UserBusinessAccess
from apps.businesses.models import Business, BusinessTemplate
from apps.businesses.services import save_brand_version, approve_brand
from apps.connections.models import Competitor, SocialAccount
from apps.content.models import ContentItem, ContentTarget

DEMO = [
    ("Bilim Markazi", "oquv_markaz", "O'quv markaz", "Toshkent", "Ingliz tili va IT kurslari. 3 oylik kurs.", "450 000 so'm/oy"),
    ("Moda Uyi", "kiyim_dokoni", "Kiyim do'koni", "Samarqand", "Ayollar va erkaklar kiyimi, mavsumiy kolleksiya.", "150 000 – 900 000 so'm"),
    ("TexnoServis", "kompyuter_xizmatlari", "Kompyuter xizmatlari", "Toshkent", "Kompyuter ta'mirlash, tarmoq, B2B xizmat.", "50 000 so'mdan"),
]


class Command(BaseCommand):
    help = "Demo ma'lumotlar (3 biznes, soxta ulanishlar, metrikalar). Faqat USE_FAKES=1 bilan haqiqiy tarmoqsiz ishlaydi."

    def handle(self, *a, **o):
        from django.conf import settings
        if not settings.USE_FAKES:
            self.stderr.write("Demo uchun .env da USE_FAKES=1 qo'ying (haqiqiy ulanishlarga tegmaslik uchun).")
            return
        call_command("bootstrap")
        from apps.jobs.queue import enqueue  # noqa: F401
        from apps.metrics import collector
        for name, tpl, industry, region, desc, price in DEMO:
            b, new = Business.objects.get_or_create(name=name, defaults=dict(template=BusinessTemplate.objects.filter(key=tpl).first(), industry=industry, region=region,
                                                                                description=desc, price_range=price, main_goal="lead", monthly_ad_budget=3_000_000, avg_check=450_000,
                                                                                facts={"telefon": "+998 90 123 45 67", "narx": price}))
            if not new:
                continue
            bp = save_brand_version(b, f"Sen «{name}» brendining SMM mutaxassisisan. Ohang: samimiy, aniq, hurmatli. Til: o'zbek (lotin).\nSoha: {industry}. {desc}", user=None)
            approve_brand(bp, None)
            for plat in ("telegram", "instagram", "youtube"):
                acc = SocialAccount(business=b, platform=plat, name=f"{name} · {plat}", handle=name.lower().replace(" ", "_"), external_id=f"fake-{b.pk}-{plat}", status="active")
                acc.set_credentials({"access_token": "fake", "chat": "@demo"})
                acc.save()
                try:
                    collector.collect_account(acc, mode="history", days=60)
                except Exception as e:  # noqa: BLE001
                    self.stderr.write(f"{acc}: {e}")
            Competitor.objects.get_or_create(business=b, platform="telegram", handle="raqobatchi_demo", defaults={"name": "Raqobatchi (demo)"})
            tg = b.accounts.filter(platform="telegram").first()
            for i in range(3):
                it = ContentItem.objects.create(business=b, title=f"Demo post {i + 1}", text=f"{name}: yangi imkoniyat! Batafsil: +998 90 123 45 67", media_type="text",
                                                scheduled_at=timezone.now() + timedelta(days=i + 1, hours=3), status="draft")
                ContentTarget.objects.create(item=it, account=tg)
        role = Role.objects.filter(name="Menejer").first()
        if role and not User.objects.filter(username="menejer").exists():
            u = User.objects.create_user("menejer", password="Menejer#2026demo", full_name="Demo Menejer")
            for b in Business.objects.all()[:2]:
                UserBusinessAccess.objects.create(user=u, business=b, role=role)
        self.stdout.write(self.style.SUCCESS("Demo tayyor. Kirish: o'zingiz yaratgan admin; demo menejer: menejer / Menejer#2026demo"))
