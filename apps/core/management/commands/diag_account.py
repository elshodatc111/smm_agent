"""Hisob bo'yicha yig'ish diagnostikasi: platformadan nima qaytayapti va bazada nima bor. Maxfiy ma'lumot chiqarmaydi."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "manage.py diag_account [--platform youtube] [--id N]"

    def add_arguments(self, p):
        p.add_argument("--platform", default="")
        p.add_argument("--id", type=int, default=0)

    def handle(self, *a, **o):
        from apps.connections.models import SocialAccount
        from apps.metrics.collector import get_connector
        from apps.metrics.models import AccountMetrics, CollectionRun, Post, PostMetricsHistory
        qs = SocialAccount.objects.all()
        if o["id"]:
            qs = qs.filter(pk=o["id"])
        if o["platform"]:
            qs = qs.filter(platform=o["platform"])
        for acc in qs:
            self.stdout.write(f"\n=== Hisob #{acc.pk} {acc.platform} {acc.handle} (holat: {acc.status}) ===")
            am = AccountMetrics.objects.filter(account=acc).order_by("-taken_at")
            self.stdout.write(f"Bazada: hisob statistikasi {am.count()} ta, postlar {Post.objects.filter(account=acc).count()} ta, "
                              f"post metrikalari {PostMetricsHistory.objects.filter(post__account=acc).count()} ta")
            last = am.first()
            if last:
                self.stdout.write(f"Oxirgi: obunachi={last.followers} ko'rish={last.views} postlar={last.posts_count} extra={last.extra}")
            for r in CollectionRun.objects.filter(account=acc).order_by("-at")[:5]:
                self.stdout.write(f"  yig'ish {r.at:%d.%m %H:%M} {r.kind} ok={r.ok} items={r.items} xato={r.error[:150]}")
            self.stdout.write("Platformadan jonli so'rov:")
            try:
                conn = get_connector(acc)
                st = conn.fetch_account_stats()
                self.stdout.write(f"  hisob: obunachi={st.followers} ko'rish={st.views} postlar={st.posts_count} extra={st.extra}")
                page = conn.fetch_posts(timezone.now() - timedelta(days=3650), None)
                self.stdout.write(f"  postlar (1-sahifa): {len(page.items)} ta, keyingi sahifa: {bool(page.next_cursor)}")
                for pd in page.items[:5]:
                    self.stdout.write(f"    - {pd.published_at:%d.%m.%Y} {str(pd.media_type)} {pd.text[:50]!r}")
                if page.items:
                    ms = conn.fetch_post_metrics([page.items[0].external_id])
                    if ms:
                        m = ms[0]
                        self.stdout.write(f"  1-post metrikasi: ko'rish={m.views} like={m.likes} izoh={m.comments} watch_sec={m.watch_time_sec}")
            except Exception as e:  # noqa: BLE001
                self.stdout.write(f"  XATO: {getattr(e, 'user_message_uz', '') or str(e)[:300]}")
