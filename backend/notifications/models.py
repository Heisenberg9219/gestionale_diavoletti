from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class Notification(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        STOCK_DEPLETED = "STOCK_DEPLETED", "Articolo esaurito"
        REORDER = "REORDER", "Riordino"
        VOUCHER_EXPIRING = "VOUCHER_EXPIRING", "Buono in scadenza"
        EXPENSE_DUE = "EXPENSE_DUE", "Scadenza spesa"
        GIFT_LIST = "GIFT_LIST", "Lista regalo"
        SYSTEM = "SYSTEM", "Sistema"

    class Priority(models.TextChoices):
        LOW = "LOW", "Bassa"
        NORMAL = "NORMAL", "Normale"
        HIGH = "HIGH", "Alta"
        CRITICAL = "CRITICAL", "Critica"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Attiva"
        RESOLVED = "RESOLVED", "Risolta"

    notification_type = models.CharField(max_length=24, choices=Type.choices)
    priority = models.CharField(
        max_length=16,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    title = models.CharField(max_length=180)
    message = models.TextField()
    deduplication_key = models.CharField(max_length=180)
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    action_path = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resolved_notifications",
    )
    resolution_notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-occurred_at", "-created_at")
        indexes = [
            models.Index(
                fields=("status", "priority", "occurred_at"),
                name="notif_status_priority_idx",
            ),
            models.Index(
                fields=("source_type", "source_id"),
                name="notif_source_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("deduplication_key",),
                condition=Q(status="ACTIVE"),
                name="notif_active_dedupe_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(source_type="", source_id__isnull=True)
                    | (~Q(source_type="") & Q(source_id__isnull=False))
                ),
                name="notif_source_pair_valid",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="RESOLVED")
                    | Q(resolved_at__isnull=False, resolved_by__isnull=False)
                ),
                name="notif_resolved_audit",
            ),
        ]

    def __str__(self):
        return self.title


class NotificationDelivery(UUIDTimeStampedModel):
    notification = models.ForeignKey(
        Notification,
        on_delete=models.PROTECT,
        related_name="deliveries",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notification_deliveries",
    )
    matched_role_codes = models.JSONField(default=list)
    delivered_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-delivered_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("notification", "user"),
                name="notif_delivery_user_unique",
            ),
        ]

    @property
    def is_read(self):
        return self.read_at is not None

    @property
    def is_archived(self):
        return self.archived_at is not None

    def __str__(self):
        return f"{self.user.email} - {self.notification.title}"


class NotificationResolution(UUIDTimeStampedModel):
    notification = models.OneToOneField(
        Notification,
        on_delete=models.PROTECT,
        related_name="resolution",
    )
    resolved_at = models.DateTimeField(default=timezone.now)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notification_resolution_records",
    )
    notes = models.CharField(max_length=255)

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("La risoluzione della notifica è immutabile.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La risoluzione della notifica è immutabile.")
