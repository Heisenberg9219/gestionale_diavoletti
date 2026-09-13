import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser, Group
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'email è obbligatoria.")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", "ACTIVE")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superutente deve avere is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superutente deve avere is_superuser=True.")

        return self.create_user(email, password, **extra_fields)

class RoleMetadata(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    group = models.OneToOneField(
        Group,
        on_delete=models.PROTECT,
        related_name="role_metadata",
    )
    code = models.CharField(max_length=32, unique=True)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code

class User(AbstractUser):
    class Status(models.TextChoices):
        INVITED = "INVITED", "Invitato"
        ACTIVE = "ACTIVE", "Attivo"
        BLOCKED = "BLOCKED", "Bloccato"
        ARCHIVED = "ARCHIVED", "Archiviato"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    username = None
    email = models.EmailField(unique=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class UserPagePermission(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="page_permissions"
    )
    page_key = models.CharField(max_length=48)
    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_update = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    class Meta:
        ordering = ("page_key",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "page_key"), name="accounts_user_page_permission_unique"
            )
        ]
