import logging

from django.core.management.base import BaseCommand

from apps.jobs.worker import Worker


class Command(BaseCommand):
    help = "Fon vazifalari worker jarayoni (navbat + jadval + mijoz boti)."

    def add_arguments(self, p):
        p.add_argument("--no-bot", action="store_true")

    def handle(self, *a, **o):
        logging.getLogger().info("Worker boshlandi")
        Worker().run_forever(with_bot=not o["no_bot"])
