from __future__ import annotations

from django.core.cache import cache

from .models import Role, RolePermission, User, UserBusinessAccess, UserPermissionOverride
from .permissions_registry import ADMIN_ONLY, GLOBAL_MODULES, validate


def bump_permissions(user: User | None = None) -> None:
    """Ruxsat o'zgarganda keshni darhol bekor qiladi (qayta kirish kerak emas)."""
    cache.set("perm_epoch", cache.get("perm_epoch", 0) + 1, None)


class PermissionService:
    def _role_codes(self, role_id: int) -> set[str]:
        key = f"rolecodes:{cache.get('perm_epoch', 0)}:{role_id}"
        v = cache.get(key)
        if v is None:
            v = set(RolePermission.objects.filter(role_id=role_id).values_list("code", flat=True))
            cache.set(key, v, 300)
        return v

    def _overrides(self, user: User):
        allow, deny = set(), set()
        for o in UserPermissionOverride.objects.filter(user=user):
            (allow if o.allow else deny).add(o.code)
        return allow, deny

    def _access_role_ids(self, user: User, business_id: int | None) -> list[int]:
        qs = UserBusinessAccess.objects.filter(user=user)
        if business_id is None:
            return list(qs.values_list("role_id", flat=True))
        ids = list(qs.filter(business_id=business_id).values_list("role_id", flat=True))
        ids += list(qs.filter(all_flag=True, business__isnull=True).values_list("role_id", flat=True))
        return ids

    def can(self, user: User, code: str, business=None) -> bool:
        validate(code)
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.is_admin:
            return True
        if code in ADMIN_ONLY:      # sozlamalar, foydalanuvchilar, yangi biznes/akkaunt ulash: rol yoki individual ruxsat bilan ham berilmaydi
            return False
        module = code.split(".")[0]
        bid = getattr(business, "pk", business)
        if module in GLOBAL_MODULES:
            bid = None
        elif bid is None:
            return False
        allow, deny = self._overrides(user)
        if code in deny:
            return False
        if code in allow:
            return bid is None or self.has_business(user, bid)
        for rid in self._access_role_ids(user, bid):
            if code in self._role_codes(rid):
                return True
        return False

    def has_business(self, user: User, business_id: int) -> bool:
        if user.is_admin:
            return True
        qs = UserBusinessAccess.objects.filter(user=user)
        return qs.filter(business_id=business_id).exists() or qs.filter(all_flag=True, business__isnull=True).exists()

    def businesses_for(self, user: User, code: str | None = None):
        from apps.businesses.models import Business
        if user.is_admin:
            return Business.objects.filter(archived_at__isnull=True)
        qs = UserBusinessAccess.objects.filter(user=user)
        if qs.filter(all_flag=True, business__isnull=True).exists():
            base = Business.objects.filter(archived_at__isnull=True)
        else:
            base = Business.objects.filter(archived_at__isnull=True, pk__in=qs.exclude(business=None).values("business_id"))
        if code:
            ids = [b.pk for b in base if self.can(user, code, b)]
            return base.filter(pk__in=ids)
        return base


perms = PermissionService()


def guard_admin_change(user: User, *, deactivating=False, demoting=False) -> None:
    """Oxirgi faol adminni o'chirish/pasaytirishni taqiqlaydi."""
    if (deactivating or demoting) and user.is_admin:
        if not User.objects.filter(is_admin=True, is_active=True).exclude(pk=user.pk).exists():
            raise PermissionError("Tizimda kamida bitta faol admin bo'lishi shart.")


def delete_role(role: Role) -> None:
    if role.is_system:
        raise PermissionError("Tizim rolini o'chirib bo'lmaydi.")
    if role.accesses.exists():
        raise PermissionError("Bu rolga foydalanuvchilar biriktirilgan; avval ularni ko'chiring.")
    role.delete()
    bump_permissions()


def set_role_permissions(role: Role, codes: set[str]) -> None:
    for c in codes:
        validate(c)
    RolePermission.objects.filter(role=role).exclude(code__in=codes).delete()
    for c in codes:
        RolePermission.objects.get_or_create(role=role, code=c)
    bump_permissions()
