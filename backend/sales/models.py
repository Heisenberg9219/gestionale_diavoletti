from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class SaleDraftChange(UUIDTimeStampedModel):
    sale = models.ForeignKey("Sale", on_delete=models.PROTECT, related_name="draft_changes")
    operation = models.CharField(max_length=32, choices=[("REMOVE_LINE", "Rimozione riga"), ("REMOVE_PAYMENT", "Rimozione pagamento"), ("CANCEL", "Annullamento")])
    reason = models.CharField(max_length=255)
    snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ("created_at", "pk")


class CashRegister(UUIDTimeStampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        related_name="cash_registers",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.code} - {self.name}"


class CashSession(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Aperta"
        CLOSED = "CLOSED", "Chiusa"

    cash_register = models.ForeignKey(
        CashRegister,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    opened_at = models.DateTimeField(default=timezone.now)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="opened_cash_sessions",
    )
    opening_cash_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="closed_cash_sessions",
    )
    expected_cash_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    counted_cash_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cash_difference = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-opened_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("cash_register",),
                condition=Q(status="OPEN"),
                name="sales_one_open_session_per_register",
            ),
            models.CheckConstraint(
                condition=Q(opening_cash_amount__gte=0),
                name="sales_opening_cash_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(expected_cash_amount__isnull=True)
                    | Q(expected_cash_amount__gte=0)
                ),
                name="sales_expected_cash_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(counted_cash_amount__isnull=True)
                    | Q(counted_cash_amount__gte=0)
                ),
                name="sales_counted_cash_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(closed_at__isnull=True)
                    | Q(closed_at__gte=F("opened_at"))
                ),
                name="sales_cash_session_dates_valid",
            ),
        ]

    def __str__(self):
        return f"{self.cash_register.code} - {self.opened_at}"

class SaleNumberSequence(UUIDTimeStampedModel):
    year = models.PositiveSmallIntegerField(unique=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-year",)

    def __str__(self):
        return f"{self.year}: {self.last_number}"
    
class Sale(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Aperta"
        CONFIRMED = "CONFIRMED", "Confermata"
        CANCELLED = "CANCELLED", "Annullata"

    class Channel(models.TextChoices):
        POS = "POS", "Negozio"
        SHOPIFY = "SHOPIFY", "Shopify"

    number = models.CharField(max_length=32, blank=True)
    channel = models.CharField(
        max_length=16,
        choices=Channel.choices,
        default=Channel.POS,
    )
    cash_session = models.ForeignKey(
        CashSession,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales",
    )
    location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        related_name="sales",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    opened_at = models.DateTimeField(default=timezone.now)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="opened_sales",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="confirmed_sales",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_sales",
    )
    subtotal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    calculated_total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    manual_total_override_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    manual_total_adjustment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    final_total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_cost_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    manual_override_reason = models.CharField(
        max_length=255,
        blank=True,
    )
    manual_override_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="manually_overridden_sales",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-opened_at",)
        indexes = [
            models.Index(
                fields=("status", "confirmed_at"),
                name="sales_status_confirmed_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("number",),
                condition=~Q(number=""),
                name="sales_number_unique_when_present",
            ),
            models.CheckConstraint(
                condition=(
                    Q(subtotal_amount__gte=0)
                    & Q(discount_amount__gte=0)
                    & Q(tax_amount__gte=0)
                    & Q(calculated_total_amount__gte=0)
                    & Q(final_total_amount__gte=0)
                    & Q(total_cost_amount__gte=0)
                ),
                name="sales_totals_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(manual_total_override_amount__isnull=True)
                    | Q(manual_total_override_amount__gte=0)
                ),
                name="sales_manual_total_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="CONFIRMED")
                    | ~Q(number="")
                ),
                name="sales_confirmed_number_required",
            ),
        ]

    def __str__(self):
        return self.number or f"Vendita aperta {self.id}"

class SaleLine(UUIDTimeStampedModel):
    class PricingMode(models.TextChoices):
        STANDARD = "STANDARD", "Prezzo normale"
        SALE = "SALE", "Saldo"
        PROMOTION = "PROMOTION", "Promozione"

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="sale_lines",
    )
    quantity = models.PositiveIntegerField()
    sku_snapshot = models.CharField(max_length=64)
    product_name_snapshot = models.CharField(max_length=160)
    color_snapshot = models.CharField(max_length=120, blank=True)
    size_snapshot = models.CharField(max_length=32, blank=True)
    pricing_mode = models.CharField(
        max_length=16,
        choices=PricingMode.choices,
        default=PricingMode.STANDARD,
    )
    source_sale_price = models.ForeignKey(
        "pricing.VariantSalePrice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sale_lines",
    )
    base_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    manual_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    final_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    gross_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    net_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    tax_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    unit_cost_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    total_cost_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    manual_adjustment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_override_share = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    manual_override_reason = models.CharField(
        max_length=255,
        blank=True,
    )
    manual_override_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="manually_overridden_sale_lines",
    )

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("sale", "variant"),
                name="sales_sale_variant_unique",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="sales_line_quantity_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(base_unit_price__gte=0)
                    & Q(final_unit_price__gte=0)
                    & Q(gross_amount__gte=0)
                    & Q(discount_amount__gte=0)
                    & Q(net_amount__gte=0)
                    & Q(tax_amount__gte=0)
                    & Q(unit_cost_snapshot__gte=0)
                    & Q(total_cost_amount__gte=0)
                ),
                name="sales_line_amounts_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(manual_unit_price__isnull=True)
                    | Q(manual_unit_price__gte=0)
                ),
                name="sales_line_manual_price_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(tax_percentage__gte=0)
                    & Q(tax_percentage__lte=100)
                ),
                name="sales_line_tax_percentage_valid",
            ),
        ]

    def __str__(self):
        return (
            f"{self.sale} - {self.sku_snapshot} "
            f"x {self.quantity}"
        )

class SalePayment(UUIDTimeStampedModel):
    class Method(models.TextChoices):
        CASH = "CASH", "Contanti"
        CARD = "CARD", "Carta"
        GIFT_CARD = "GIFT_CARD", "Gift card"
        STORE_CREDIT = "STORE_CREDIT", "Buono reso"
        OTHER = "OTHER", "Altro"

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    method = models.CharField(
        max_length=24,
        choices=Method.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    cash_received_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cash_change_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    transaction_reference = models.CharField(
        max_length=120,
        blank=True,
    )
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_sale_payments",
    )

    class Meta:
        ordering = ("occurred_at", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="sales_payment_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        method="CASH",
                        cash_received_amount__gte=F("amount"),
                        cash_change_amount=(
                            F("cash_received_amount") - F("amount")
                        ),
                    )
                    | Q(
                        ~Q(method="CASH"),
                        cash_received_amount__isnull=True,
                        cash_change_amount__isnull=True,
                    )
                ),
                name="sales_payment_cash_fields_valid",
            ),
        ]

    def __str__(self):
        return f"{self.sale} - {self.method}: {self.amount}"
