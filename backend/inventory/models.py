from decimal import Decimal

from django.db import models
from django.db.models import Q

from core.models import UUIDTimeStampedModel


class StockBalance(UUIDTimeStampedModel):
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    quantity_on_hand = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("location", "variant")
        constraints = [
            models.UniqueConstraint(
                fields=("variant", "location"),
                name="inventory_variant_location_unique",
            ),
        ]

    def __str__(self):
        return (
            f"{self.variant.sku} - {self.location.code}: "
            f"{self.quantity_on_hand}"
        )


class VariantInventoryCost(UUIDTimeStampedModel):
    variant = models.OneToOneField(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="inventory_cost",
    )
    weighted_average_unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    total_quantity = models.PositiveIntegerField(default=0)
    inventory_value = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    last_movement_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("variant",)
        constraints = [
            models.CheckConstraint(
                condition=Q(weighted_average_unit_cost__gte=0),
                name="inventory_weighted_cost_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(inventory_value__gte=0),
                name="inventory_value_non_negative",
            ),
        ]

    def __str__(self):
        return (
            f"{self.variant.sku} - "
            f"{self.weighted_average_unit_cost}"
        )

class StockMovement(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        INITIAL_STOCK = "INITIAL_STOCK", "Carico iniziale"
        PURCHASE_RECEIPT = "PURCHASE_RECEIPT", "Ricezione fornitore"
        SALE = "SALE", "Vendita"
        CUSTOMER_RETURN = "CUSTOMER_RETURN", "Reso cliente"
        SUPPLIER_RETURN = "SUPPLIER_RETURN", "Reso fornitore"
        TRANSFER_IN = "TRANSFER_IN", "Trasferimento in entrata"
        TRANSFER_OUT = "TRANSFER_OUT", "Trasferimento in uscita"
        ADJUSTMENT_IN = "ADJUSTMENT_IN", "Rettifica in entrata"
        ADJUSTMENT_OUT = "ADJUSTMENT_OUT", "Rettifica in uscita"
        INVENTORY_GAIN = "INVENTORY_GAIN", "Eccedenza inventario"
        INVENTORY_LOSS = "INVENTORY_LOSS", "Ammanco inventario"

    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    movement_type = models.CharField(
        max_length=24,
        choices=Type.choices,
    )
    quantity_delta = models.IntegerField()
    unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    occurred_at = models.DateTimeField()
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    reference_number = models.CharField(max_length=120, blank=True)
    transfer_group_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_stock_movements",
    )

    class Meta:
        ordering = ("-occurred_at", "-created_at")
        indexes = [
            models.Index(
                fields=("variant", "occurred_at"),
                name="inv_move_variant_date_idx",
            ),
            models.Index(
                fields=("location", "occurred_at"),
                name="inv_move_location_date_idx",
            ),
            models.Index(
                fields=("source_type", "source_id"),
                name="inventory_move_source_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity_delta=0),
                name="inventory_movement_quantity_non_zero",
            ),
            models.CheckConstraint(
                condition=(
                    Q(unit_cost__isnull=True)
                    | Q(unit_cost__gte=0)
                ),
                name="inventory_movement_unit_cost_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        movement_type__in=(
                            "INITIAL_STOCK",
                            "PURCHASE_RECEIPT",
                            "CUSTOMER_RETURN",
                            "TRANSFER_IN",
                            "ADJUSTMENT_IN",
                            "INVENTORY_GAIN",
                        ),
                        quantity_delta__gt=0,
                    )
                    | Q(
                        movement_type__in=(
                            "SALE",
                            "SUPPLIER_RETURN",
                            "TRANSFER_OUT",
                            "ADJUSTMENT_OUT",
                            "INVENTORY_LOSS",
                        ),
                        quantity_delta__lt=0,
                    )
                ),
                name="inventory_movement_type_quantity_sign_valid",
            ),
        ]

    def __str__(self):
        return (
            f"{self.variant.sku} - {self.movement_type}: "
            f"{self.quantity_delta}"
        )


class InventoryCountSession(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Bozza"
        IN_PROGRESS = "IN_PROGRESS", "In corso"
        CONFIRMED = "CONFIRMED", "Confermato"
        CANCELLED = "CANCELLED", "Annullato"

    class Scope(models.TextChoices):
        FULL = "FULL", "Inventario completo"
        PARTIAL = "PARTIAL", "Inventario parziale"

    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        related_name="inventory_count_sessions",
    )
    scope = models.CharField(max_length=16, choices=Scope.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField(blank=True)
    brands = models.ManyToManyField(
        "catalog.Brand",
        blank=True,
        related_name="inventory_count_sessions",
    )
    categories = models.ManyToManyField(
        "catalog.Category",
        blank=True,
        related_name="inventory_count_sessions",
    )
    seasons = models.ManyToManyField(
        "catalog.Season",
        blank=True,
        related_name="inventory_count_sessions",
    )
    products = models.ManyToManyField(
        "catalog.Product",
        blank=True,
        related_name="inventory_count_sessions",
    )
    variants = models.ManyToManyField(
        "catalog.ProductVariant",
        blank=True,
        related_name="inventory_count_sessions",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_inventory_count_sessions",
    )
    confirmed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="confirmed_inventory_count_sessions",
    )
    cancelled_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_inventory_count_sessions",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("location", "status", "created_at"),
                name="inv_count_loc_status_idx",
            ),
            models.Index(
                fields=("confirmed_at",),
                name="inv_count_confirmed_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status="CONFIRMED", confirmed_at__isnull=False,
                      confirmed_by__isnull=False)
                    | ~Q(status="CONFIRMED")
                ),
                name="inv_count_confirmed_audit",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="CANCELLED", cancelled_at__isnull=False,
                      cancelled_by__isnull=False)
                    | ~Q(status="CANCELLED")
                ),
                name="inv_count_cancelled_audit",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class InventoryCountLine(UUIDTimeStampedModel):
    session = models.ForeignKey(
        InventoryCountSession,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="inventory_count_lines",
    )
    expected_quantity = models.PositiveIntegerField()
    counted_quantity = models.PositiveIntegerField(null=True, blank=True)
    difference_quantity = models.IntegerField(null=True, blank=True)
    unit_cost_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    expected_value = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    counted_value = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )
    difference_value = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )
    counted_at = models.DateTimeField(null=True, blank=True)
    counted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="counted_inventory_lines",
    )
    adjustment_movement = models.OneToOneField(
        StockMovement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_count_line",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("variant",)
        constraints = [
            models.UniqueConstraint(
                fields=("session", "variant"),
                name="inv_count_session_variant_unique",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost_snapshot__gte=0),
                name="inv_count_unit_cost_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(expected_value__gte=0),
                name="inv_count_expected_value_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(counted_quantity__isnull=True,
                      difference_quantity__isnull=True,
                      counted_value__isnull=True,
                      difference_value__isnull=True,
                      counted_at__isnull=True,
                      counted_by__isnull=True)
                    | Q(counted_quantity__isnull=False,
                        difference_quantity__isnull=False,
                        counted_value__isnull=False,
                        difference_value__isnull=False,
                        counted_at__isnull=False,
                        counted_by__isnull=False)
                ),
                name="inv_count_line_count_audit",
            ),
        ]

    def __str__(self):
        return f"{self.session.code} - {self.variant.sku}"
