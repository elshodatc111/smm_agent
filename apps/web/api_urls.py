from django.http import JsonResponse
from django.urls import path

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.core.models import Notification
from apps.web.context import session_payload


def health(request):
    """Ochiq, minimal: watchdog va monitoring uchun."""
    from apps.health import services as hs
    q = hs.queue()
    return JsonResponse({"ok": True, "worker_alive": q["worker_alive"]})


@require_permission("dashboard.view")
def businesses(request):
    return JsonResponse({"data": [{"id": b.pk, "name": b.name} for b in perms.businesses_for(request.user, "dashboard.view")]})


@require_permission("notifications.view")
def unread(request):
    return JsonResponse({"unread": Notification.objects.filter(user=request.user, read_at__isnull=True).count()})


def session(request):
    """React ilovasi uchun: brend, foydalanuvchi, menyu, bizneslar (kirmagan bo'lsa faqat brend)."""
    return JsonResponse(session_payload(request), json_dumps_params={"ensure_ascii": False})


urlpatterns = [
    path("session/", session),
    path("health/", health),
    path("businesses/", businesses),
    path("notifications/unread/", unread),
]
