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