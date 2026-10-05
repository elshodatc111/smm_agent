"""Biznes kontekstida queryset olish (xom .objects.all() o'rniga)."""
from apps.accounts.services import perms


def scoped(model, user, business=None, code=None):
    """model biznesga tegishli (business FK). business berilsa faqat shu; aks holda foydalanuvchi ko'ra oladigan hammasi."""
    if business is not None:
        if not perms.has_business(user, business.pk):
            return model.objects.none()
        return model.objects.filter(business=business)
    ids = perms.businesses_for(user, code).values_list("pk", flat=True)
    return model.objects.filter(business_id__in=list(ids))
