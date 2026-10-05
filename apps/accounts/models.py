from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.Model):
    name = models.CharField(max_length=60, unique=True)
    description = models.CharField(max_length=200, blank=True)
    is_system = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    code = models.CharField(max_length=60)

    class Meta:
        unique_together = [("role", "code")]


class User(AbstractUser):
    is_admin = models.BooleanField(default=False, help_text="Tizim administratori (to'liq huquq)")
    full_name = models.CharField(max_length=120, blank=True)
    telegram_id = models.BigIntegerField(null=True, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    theme = models.CharField(max_length=10, default="")  # '', light, dark
    perm_version = models.PositiveIntegerField(default=1)

    def display(self):
        return self.full_name or self.username


class UserBusinessAccess(models.Model):
    """business=None va all_flag=True -> «Barcha bizneslar» (shu rol bilan)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="accesses")
    business = models.ForeignKey("businesses.Business", null=True, blank=True, on_delete=models.CASCADE, related_name="accesses")
    all_flag = models.BooleanField(default=False)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="accesses")

    class Meta:
        unique_together = [("user", "business")]


class UserPermissionOverride(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="overrides")
    code = models.CharField(max_length=60)
    allow = models.BooleanField(default=True)

    class Meta:
        unique_together = [("user", "code")]
