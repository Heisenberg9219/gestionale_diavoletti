from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class CustomerReturnNumberSequence(UUIDTimeStampedModel):
    year = models.PositiveSmallIntegerField(unique=True)
    last_number = models.PositiveIntegerField(default=0)


class CustomerReturn(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Bozza"
        CONFIRMED = "CONFIRMED", "Confermato"
        CANCELLED = "CANCELLED", "Annullato"

    number = models.CharField(max_length=32, blank=True)
    original_sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.PROTECT,
        related_name="customer_returns",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="returns",
    )
    location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        related_name="customer_returns",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    reason = models.CharField(max_length=255)
    total_refund_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    points_reversed = models.PositiveIntegerField(default=0)
    return_voucher = models.OneToOneField(
        "vouchers.Voucher",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="source_customer_return",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_customer_returns",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="confirmed_customer_returns",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_customer_returns",
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("number",),
                condition=~Q(number=""),
                name="return_number_unique",
            ),
            models.CheckConstraint(
                condition=Q(total_refund_amount__gte=0),
                name="return_refund_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="CONFIRMED")
                    | Q(
                        number__gt="",
                        confirmed_at__isnull=False,
                        confirmed_by__isnull=False,
                        return_voucher__isnull=False,
                        total_refund_amount__gt=0,
                    )
                ),
                name="return_confirmed_audit",
            ),
        ]

    def __str__(self):
        return self.number or f"Reso in bozza {self.id}"


class CustomerReturnLine(UUIDTimeStampedModel):
    customer_return = models.ForeignKey(
        CustomerReturn,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    original_sale_line = models.ForeignKey(
        "sales.SaleLine",
        on_delete=models.PROTECT,
        related_name="return_lines",
    )
    quantity = models.PositiveIntegerField()
    restock = models.BooleanField(default=True)
    unit_refund_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_refund_amount = models.DecimalField(max_digits=12, decimal_places=2)
    sku_snapshot = models.CharField(max_length=64)
    product_name_snapshot = models.CharField(max_length=160)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("customer_return", "original_sale_line"),
                name="return_line_sale_line_unique",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="return_line_quantity_pos",
            ),
            models.CheckConstraint(
                condition=(
                    Q(unit_refund_amount__gte=0)
                    & Q(total_refund_amount__gt=0)
                ),
                name="return_line_amounts_valid",
            ),
        ]

    def __str__(self):
        return f"{self.customer_return} - {self.sku_snapshot}"
