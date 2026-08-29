import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class UUIDTimeStampedModel(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ShopSettings(UUIDTimeStampedModel):
    class PriceRoundingStrategy(models.TextChoices):
        NEAREST_90 = "NEAREST_90", "Finale ,90 più vicino"

    singleton_key = models.BooleanField(
        default=True,
        unique=True,
        editable=False,
    )
    shop_name = models.CharField(max_length=160)
    timezone = models.CharField(
        max_length=64,
        default="Europe/Rome",
    )
    currency_code = models.CharField(
        max_length=3,
        default="EUR",
    )
    default_markup = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("2.500"),
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    return_credit_months = models.PositiveSmallIntegerField(
        default=6,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(120),
        ],
    )
    price_rounding_strategy = models.CharField(
        max_length=24,
        choices=PriceRoundingStrategy.choices,
        default=PriceRoundingStrategy.NEAREST_90,
    )

    def __str__(self):
        return self.shop_name


class Location(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        SALES_FLOOR = "SALES_FLOOR", "Area vendita"
        STOCKROOM = "STOCKROOM", "Magazzino interno"
        OTHER = "OTHER", "Altro"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=24, choices=Type.choices)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class TaxRate(UUIDTimeStampedModel):
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=120)
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="core_single_default_tax_rate",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.percentage}%)"