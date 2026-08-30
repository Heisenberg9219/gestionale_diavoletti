from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class VariantSalePrice(UUIDTimeStampedModel):
    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manuale"
        SUGGESTED = "SUGGESTED", "Prezzo suggerito"
        IMPORT = "IMPORT", "Importazione"

    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="sale_prices",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.MANUAL,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_variant_sale_prices",
    )

    class Meta:
        ordering = ("variant", "-valid_from")
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="pricing_sale_price_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(valid_until__isnull=True)
                    | Q(valid_until__gt=F("valid_from"))
                ),
                name="pricing_sale_price_dates_valid",
            ),
            models.UniqueConstraint(
                fields=("variant",),
                condition=Q(valid_until__isnull=True),
                name="pricing_one_current_sale_price_per_variant",
            ),
        ]

    def __str__(self):
        return f"{self.variant.sku} - {self.amount}"