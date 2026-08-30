from django.db import models
from django.db.models import Q

from core.models import UUIDTimeStampedModel


class Supplier(UUIDTimeStampedModel):
    code = models.CharField(max_length=32, unique=True)
    business_name = models.CharField(max_length=160)
    vat_number = models.CharField(max_length=32, blank=True)
    tax_code = models.CharField(max_length=32, blank=True)
    sdi_code = models.CharField(max_length=7, blank=True)
    pec = models.EmailField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=16, blank=True)
    city = models.CharField(max_length=120, blank=True)
    province = models.CharField(max_length=64, blank=True)
    country_code = models.CharField(max_length=2, default="IT")
    payment_terms = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("business_name",)
        constraints = [
            models.UniqueConstraint(
                fields=("vat_number",),
                condition=~Q(vat_number=""),
                name="suppliers_vat_number_unique_when_present",
            ),
            models.UniqueConstraint(
                fields=("tax_code",),
                condition=~Q(tax_code=""),
                name="suppliers_tax_code_unique_when_present",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.business_name}"

class SupplierVariant(UUIDTimeStampedModel):
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="variant_links",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="supplier_links",
    )
    supplier_product_code = models.CharField(max_length=80, blank=True)
    is_preferred = models.BooleanField(default=False)
    minimum_order_quantity = models.PositiveIntegerField(default=1)
    lead_time_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("supplier", "variant")
        constraints = [
            models.UniqueConstraint(
                fields=("supplier", "variant"),
                name="suppliers_supplier_variant_unique",
            ),
            models.UniqueConstraint(
                fields=("variant",),
                condition=Q(is_preferred=True),
                name="suppliers_one_preferred_supplier_per_variant",
            ),
            models.CheckConstraint(
                condition=Q(minimum_order_quantity__gte=1),
                name="suppliers_minimum_order_quantity_positive",
            ),
        ]

    def __str__(self):
        return f"{self.supplier.code} - {self.variant.sku}"