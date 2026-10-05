from .services import perms


class BusinessContextMiddleware:
    """Seansdagi tanlangan biznesni request.business ga qo'yadi (faqat kirish huquqi bo'lsa)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.business = None
        u = getattr(request, "user", None)
        if u is not None and u.is_authenticated:
            bid = request.session.get("business_id")
            if bid:
                from apps.businesses.models import Business
                b = Business.objects.filter(pk=bid, archived_at__isnull=True).first()
                if b and perms.has_business(u, b.pk):
                    request.business = b
                else:
                    request.session.pop("business_id", None)
        return self.get_response(request)


class TimezoneMiddleware:
    """Formalardagi sana/vaqt Toshkent vaqti (sozlamadagi general.timezone) bo'yicha o'qiladi va ko'rsatiladi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.utils import timezone

        from apps.core.utils import tz
        try:
            timezone.activate(tz())
        except Exception:  # noqa: BLE001
            timezone.deactivate()
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
