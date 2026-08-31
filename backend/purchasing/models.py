from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class PurchaseOrder(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Bozza"
        SENT = "SENT", "Inviato"
        PARTIALLY_RECEIVED = (
            "PARTIALLY_RECEIVED",
            "Parzialmente ricevuto",
        )
        RECEIVED = "RECEIVED", "Ricevuto"
        CANCELLED = "CANCELLED", "Annullato"

    number = models.CharField(max_length=32, unique=True)
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    order_date = models.DateField(default=timezone.localdate)
    expected_delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_purchase_orders",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_purchase_orders",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_purchase_orders",
    )

    class Meta:
        ordering = ("-order_date", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(expected_delivery_date__isnull=True)
                    | Q(expected_delivery_date__gte=F("order_date"))
                ),
                name="purchasing_order_delivery_valid",
            ),
        ]

    def __str__(self):
        return f"{self.number} - {self.supplier.business_name}"


class PurchaseOrderLine(UUIDTimeStampedModel):
    order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="purchase_order_lines",
    )
    supplier_product_code = models.CharField(max_length=80, blank=True)
    quantity_ordered = models.PositiveIntegerField()
    expected_unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("order", "variant"),
                name="purchasing_order_variant_unique",
            ),
            models.CheckConstraint(
                condition=Q(quantity_ordered__gt=0),
                name="purchasing_order_quantity_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(expected_unit_cost__isnull=True)
                    | Q(expected_unit_cost__gte=0)
                ),
                name="purchasing_expected_cost_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.order.number} - {self.variant.sku}"

class GoodsReceipt(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Bozza"
        CONFIRMED = "CONFIRMED", "Confermata"
        CANCELLED = "CANCELLED", "Annullata"

    number = models.CharField(max_length=32, unique=True)
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="goods_receipts",
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="goods_receipts",
    )
    destination_location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        related_name="goods_receipts",
    )
    delivery_note_number = models.CharField(max_length=64, blank=True)
    delivery_note_date = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_goods_receipts",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_goods_receipts",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_goods_receipts",
    )

    class Meta:
        ordering = ("-received_at", "-created_at")

    def __str__(self):
        return f"{self.number} - {self.supplier.business_name}"


class GoodsReceiptLine(UUIDTimeStampedModel):
    receipt = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="goods_receipt_lines",
    )
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="goods_receipt_lines",
    )
    quantity_received = models.PositiveIntegerField()
    unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    final_sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("receipt", "variant"),
                name="purchasing_receipt_variant_unique",
            ),
            models.CheckConstraint(
                condition=Q(quantity_received__gt=0),
                name="purchasing_received_quantity_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(unit_cost__isnull=True)
                    | Q(unit_cost__gte=0)
                ),
                name="purchasing_receipt_cost_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(final_sale_price__isnull=True)
                    | Q(final_sale_price__gt=0)
                ),
                name="purchasing_final_price_positive",
            ),
        ]

    def __str__(self):
        return f"{self.receipt.number} - {self.variant.sku}"

class SupplierInvoice(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Bozza"
        CONFIRMED = "CONFIRMED", "Confermata"
        CANCELLED = "CANCELLED", "Annullata"

    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    invoice_number = models.CharField(max_length=64)
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    taxable_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    receipts = models.ManyToManyField(
        GoodsReceipt,
        through="SupplierInvoiceReceipt",
        related_name="supplier_invoices",
        blank=True,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_supplier_invoices",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_supplier_invoices",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_supplier_invoices",
    )

    class Meta:
        ordering = ("-invoice_date", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("supplier", "invoice_number"),
                name="purchasing_supplier_invoice_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(due_date__isnull=True)
                    | Q(due_date__gte=F("invoice_date"))
                ),
                name="purchasing_invoice_due_date_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(taxable_amount__gte=0)
                    & Q(tax_amount__gte=0)
                    & Q(total_amount__gte=0)
                ),
                name="purchasing_invoice_totals_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(
                    total_amount=F("taxable_amount") + F("tax_amount")
                ),
                name="purchasing_invoice_total_matches",
            ),
        ]

    def __str__(self):
        return (
            f"{self.invoice_number} - "
            f"{self.supplier.business_name}"
        )


class SupplierInvoiceReceipt(UUIDTimeStampedModel):
    invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.CASCADE,
        related_name="receipt_links",
    )
    receipt = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.PROTECT,
        related_name="invoice_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("invoice", "receipt"),
                name="purchasing_invoice_receipt_unique",
            ),
        ]

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.receipt.number}"

class SupplierInvoiceLine(UUIDTimeStampedModel):
    invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="supplier_invoice_lines",
    )
    receipt_line = models.ForeignKey(
        GoodsReceiptLine,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )
    quantity_invoiced = models.PositiveIntegerField()
    final_unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=4,
    )
    tax_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )
    taxable_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_invoiced__gt=0),
                name="purch_inv_line_qty_positive",
            ),
            models.CheckConstraint(
                condition=Q(final_unit_cost__gte=0),
                name="purch_inv_line_cost_nonneg",
            ),
            models.CheckConstraint(
                condition=(
                    Q(tax_percentage__gte=0)
                    & Q(tax_percentage__lte=100)
                ),
                name="purch_inv_line_tax_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(taxable_amount__gte=0)
                    & Q(tax_amount__gte=0)
                    & Q(total_amount__gte=0)
                ),
                name="purch_inv_line_totals_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(
                    total_amount=F("taxable_amount") + F("tax_amount")
                ),
                name="purch_inv_line_total_match",
            ),
        ]

    def __str__(self):
        return (
            f"{self.invoice.invoice_number} - "
            f"{self.variant.sku}"
        )


class PurchaseCostAdjustment(UUIDTimeStampedModel):
    invoice_line = models.OneToOneField(
        SupplierInvoiceLine,
        on_delete=models.PROTECT,
        related_name="cost_adjustment",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="purchase_cost_adjustments",
    )
    quantity_invoiced = models.PositiveIntegerField()
    previous_unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    final_unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=4,
    )
    total_cost_delta = models.DecimalField(
        max_digits=16,
        decimal_places=2,
    )
    remaining_quantity_affected = models.PositiveIntegerField(default=0)
    inventory_value_delta = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0,
    )
    sold_quantity_affected = models.PositiveIntegerField(default=0)
    sold_cost_delta = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0,
    )

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_invoiced__gt=0),
                name="purch_cost_adj_qty_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(previous_unit_cost__isnull=True)
                    | Q(previous_unit_cost__gte=0)
                ),
                name="purch_cost_adj_previous_valid",
            ),
            models.CheckConstraint(
                condition=Q(final_unit_cost__gte=0),
                name="purch_cost_adj_final_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    remaining_quantity_affected__lte=(
                        F("quantity_invoiced")
                        - F("sold_quantity_affected")
                    )
                ),
                name="purch_cost_adj_split_valid",
            ),
        ]

    def __str__(self):
        return (
            f"{self.variant.sku} - "
            f"rettifica {self.total_cost_delta}"
        )
