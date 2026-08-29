from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from core.models import UUIDTimeStampedModel


class Brand(UUIDTimeStampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="catalog_brand_name_ci_unique",
            ),
        ]

    def __str__(self):
        return self.name


class Category(UUIDTimeStampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("display_order", "name")

    def __str__(self):
        return self.name


class Season(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        SPRING_SUMMER = "SPRING_SUMMER", "Primavera/Estate"
        AUTUMN_WINTER = "AUTUMN_WINTER", "Autunno/Inverno"
        OTHER = "OTHER", "Altro"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    season_type = models.CharField(
        max_length=24,
        choices=Type.choices,
    )
    year = models.PositiveSmallIntegerField()
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-year", "season_type")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(start_date__isnull=True)
                    | Q(end_date__isnull=True)
                    | Q(end_date__gte=F("start_date"))
                ),
                name="catalog_season_dates_valid",
            ),
        ]

    def __str__(self):
        return self.name


class Color(UUIDTimeStampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    color_family = models.CharField(max_length=80, blank=True)
    hex_color = models.CharField(
        max_length=7,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^#[0-9A-Fa-f]{6}$",
                message="Usare il formato #RRGGBB.",
            )
        ],
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("display_order", "name")

    def __str__(self):
        return self.name


class SizeScale(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        AGE = "AGE", "Età"
        ALPHA = "ALPHA", "Alfabetica"
        ONE_SIZE = "ONE_SIZE", "Taglia unica"
        CUSTOM = "CUSTOM", "Personalizzata"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    scale_type = models.CharField(
        max_length=16,
        choices=Type.choices,
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Size(UUIDTimeStampedModel):
    size_scale = models.ForeignKey(
        SizeScale,
        on_delete=models.PROTECT,
        related_name="sizes",
    )
    code = models.CharField(max_length=32)
    label = models.CharField(max_length=32)
    min_age_months = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    max_age_months = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("size_scale", "display_order", "label")
        constraints = [
            models.UniqueConstraint(
                fields=("size_scale", "code"),
                name="catalog_size_scale_code_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(min_age_months__isnull=True)
                    | Q(max_age_months__isnull=True)
                    | Q(max_age_months__gte=F("min_age_months"))
                ),
                name="catalog_size_age_range_valid",
            ),
        ]

    def __str__(self):
        return f"{self.size_scale.name} - {self.label}"