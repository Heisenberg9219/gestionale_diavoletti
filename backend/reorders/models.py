from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class ReorderItem(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Da riordinare"
        ORDERED = "ORDERED", "Ordinato"
        COMPLETED = "COMPLETED", "Completato"
        REMOVED = "REMOVED", "Rimosso"

    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="reorder_items",
    )
    location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        related_name="reorder_items",
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reorder_items",
    )
    requested_quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="added_reorder_items",
    )
    purchase_order_line = models.ForeignKey(
        "purchasing.PurchaseOrderLine",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reorder_items",
    )
    ordered_at = models.DateTimeField(null=True, blank=True)
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ordered_reorder_items",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="completed_reorder_items",
    )
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="removed_reorder_items",
    )
    removal_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("supplier", "variant", "created_at")
        indexes = [
            models.Index(
                fields=("status", "supplier"),
                name="reorder_status_supplier_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("variant", "location"),
                condition=Q(status="PENDING"),
                name="reorder_pending_variant_loc",
            ),
            models.CheckConstraint(
                condition=Q(requested_quantity__gt=0),
                name="reorder_quantity_positive",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="ORDERED")
                    | Q(
                        purchase_order_line__isnull=False,
                        ordered_at__isnull=False,
                        ordered_by__isnull=False,
                    )
                ),
                name="reorder_ordered_audit",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="REMOVED")
                    | Q(removed_at__isnull=False, removed_by__isnull=False)
                ),
                name="reorder_removed_audit",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="COMPLETED")
                    | Q(completed_at__isnull=False, completed_by__isnull=False)
                ),
                name="reorder_completed_audit",
            ),
        ]

    def __str__(self):
        return f"{self.variant.sku} - {self.requested_quantity}"


class ReorderNotificationLink(UUIDTimeStampedModel):
    reorder_item = models.ForeignKey(
        ReorderItem,
        on_delete=models.PROTECT,
        related_name="notification_links",
    )
    notification = models.OneToOneField(
        "notifications.Notification",
        on_delete=models.PROTECT,
        related_name="reorder_link",
    )

    class Meta:
        ordering = ("created_at",)


class ReorderItemChange(UUIDTimeStampedModel):
    reorder_item = models.ForeignKey(
        ReorderItem,
        on_delete=models.PROTECT,
        related_name="changes",
    )
    previous_quantity = models.PositiveIntegerField()
    new_quantity = models.PositiveIntegerField()
    previous_supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="previous_reorder_changes",
    )
    new_supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="new_reorder_changes",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reorder_item_changes",
    )

    class Meta:
        ordering = ("created_at",)
