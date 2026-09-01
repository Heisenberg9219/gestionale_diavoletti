from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.core.exceptions import ValidationError
from core.models import UUIDTimeStampedModel


class PromotionCampaign(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        SALE = "SALE", "Saldi"
        PROMOTION = "PROMOTION", "Promozione"

    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    campaign_type = models.CharField(
        max_length=16,
        choices=Type.choices,
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_promotion_campaigns",
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.get_campaign_type_display()})"


class PromotionCampaignActivation(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        ENABLED = "ENABLED", "Abilitata"
        ENDED = "ENDED", "Terminata"
        CANCELLED = "CANCELLED", "Annullata"

    campaign = models.ForeignKey(
        PromotionCampaign,
        on_delete=models.PROTECT,
        related_name="activations",
    )
    activation_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ENABLED,
    )
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    configuration_snapshot = models.JSONField(default=dict)
    enabled_at = models.DateTimeField(auto_now_add=True)
    enabled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="enabled_promotion_activations",
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ended_promotion_activations",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_promotion_activations",
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-valid_from",)
        constraints = [
            models.UniqueConstraint(
                fields=("campaign", "activation_number"),
                name="promo_campaign_activation_number_unique",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__gt=F("valid_from")),
                name="promo_activation_dates_valid",
            ),
        ]

    def __str__(self):
        return (
            f"{self.campaign.name} - "
            f"attivazione {self.activation_number}"
        )


class PromotionRule(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        PERCENTAGE = "PERCENTAGE", "Sconto percentuale"
        FIXED_DISCOUNT = "FIXED_DISCOUNT", "Sconto fisso"
        FIXED_PRICE = "FIXED_PRICE", "Prezzo fisso"
        CHEAPEST_PERCENTAGE = (
            "CHEAPEST_PERCENTAGE",
            "Meno caro con sconto percentuale",
        )
        GROUP_FIXED_PRICE = (
            "GROUP_FIXED_PRICE",
            "Articolo del gruppo a prezzo fisso",
        )

    class GroupingMode(models.TextChoices):
        ANY_ELIGIBLE = (
            "ANY_ELIGIBLE",
            "Qualsiasi articolo idoneo",
        )
        SAME_PRODUCT = "SAME_PRODUCT", "Stesso prodotto"
        SAME_VARIANT = "SAME_VARIANT", "Stessa variante"
        SAME_CATEGORY = "SAME_CATEGORY", "Stessa categoria"
        SAME_BRAND = "SAME_BRAND", "Stessa marca"

    class TargetSelection(models.TextChoices):
        ALL = "ALL", "Tutti gli articoli"
        CHEAPEST = "CHEAPEST", "Articolo meno caro"
        MOST_EXPENSIVE = (
            "MOST_EXPENSIVE",
            "Articolo più caro",
        )
        OPERATOR_SELECTED = (
            "OPERATOR_SELECTED",
            "Scelto dall'operatore",
        )

    class FixedDiscountScope(models.TextChoices):
        PER_ITEM = "PER_ITEM", "Per ogni articolo scontato"
        PER_GROUP = "PER_GROUP", "Una volta per gruppo"
    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    rule_type = models.CharField(
        max_length=32,
        choices=Type.choices,
    )
    required_quantity = models.PositiveIntegerField(default=1)
    discounted_quantity = models.PositiveIntegerField(default=1)
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fixed_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fixed_discount_scope = models.CharField(
        max_length=16,
        choices=FixedDiscountScope.choices,
        default=FixedDiscountScope.PER_ITEM,
    )
    fixed_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    repeatable = models.BooleanField(default=False)
    grouping_mode = models.CharField(
        max_length=24,
        choices=GroupingMode.choices,
        default=GroupingMode.ANY_ELIGIBLE,
    )
    target_selection = models.CharField(
        max_length=24,
        choices=TargetSelection.choices,
        default=TargetSelection.ALL,
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(
                condition=Q(required_quantity__gt=0),
                name="promo_rule_required_qty_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(discounted_quantity__gt=0)
                    & Q(
                        discounted_quantity__lte=F(
                            "required_quantity"
                        )
                    )
                ),
                name="promo_rule_discounted_qty_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(discount_percentage__isnull=True)
                    | (
                        Q(discount_percentage__gt=Decimal("0.00"))
                        & Q(
                            discount_percentage__lte=Decimal("100.00")
                        )
                    )
                ),
                name="promo_rule_percentage_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(fixed_discount_amount__isnull=True)
                    | Q(
                        fixed_discount_amount__gt=Decimal("0.00")
                    )
                ),
                name="promo_rule_fixed_discount_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(fixed_unit_price__isnull=True)
                    | Q(fixed_unit_price__gte=Decimal("0.00"))
                ),
                name="promo_rule_fixed_price_valid",
            ),
        ]
    def clean(self):
        super().clean()

        percentage_types = {
            self.Type.PERCENTAGE,
            self.Type.CHEAPEST_PERCENTAGE,
        }
        fixed_price_types = {
            self.Type.FIXED_PRICE,
            self.Type.GROUP_FIXED_PRICE,
        }

        errors = {}

        if self.rule_type in percentage_types:
            if self.discount_percentage is None:
                errors["discount_percentage"] = (
                    "Questa regola richiede una percentuale."
                )
        elif self.discount_percentage is not None:
            errors["discount_percentage"] = (
                "La percentuale non è prevista per questa regola."
            )

        if self.rule_type == self.Type.FIXED_DISCOUNT:
            if self.fixed_discount_amount is None:
                errors["fixed_discount_amount"] = (
                    "Questa regola richiede uno sconto fisso."
                )
        elif self.fixed_discount_amount is not None:
            errors["fixed_discount_amount"] = (
                "Lo sconto fisso non è previsto per questa regola."
            )

        if self.rule_type in fixed_price_types:
            if self.fixed_unit_price is None:
                errors["fixed_unit_price"] = (
                    "Questa regola richiede un prezzo fisso."
                )
        elif self.fixed_unit_price is not None:
            errors["fixed_unit_price"] = (
                "Il prezzo fisso non è previsto per questa regola."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name

class CampaignOffer(UUIDTimeStampedModel):
    campaign = models.ForeignKey(
        PromotionCampaign,
        on_delete=models.CASCADE,
        related_name="offers",
    )
    rule = models.ForeignKey(
        PromotionRule,
        on_delete=models.PROTECT,
        related_name="campaign_offers",
    )
    code = models.CharField(max_length=48)
    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_campaign_offers",
    )

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("campaign", "code"),
                name="promo_offer_campaign_code_unique",
            ),
        ]

    def __str__(self):
        return f"{self.campaign.name} - {self.name}"

class ScopeMode(models.TextChoices):
    INCLUDE = "INCLUDE", "Includi"
    EXCLUDE = "EXCLUDE", "Escludi"


class OfferCategoryScope(UUIDTimeStampedModel):
    offer = models.ForeignKey(
        CampaignOffer,
        on_delete=models.CASCADE,
        related_name="category_scopes",
    )
    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        related_name="promotion_offer_scopes",
    )
    mode = models.CharField(
        max_length=8,
        choices=ScopeMode.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("offer", "category"),
                name="promo_offer_category_unique",
            ),
        ]

    def __str__(self):
        return f"{self.offer} - {self.category} - {self.mode}"


class OfferBrandScope(UUIDTimeStampedModel):
    offer = models.ForeignKey(
        CampaignOffer,
        on_delete=models.CASCADE,
        related_name="brand_scopes",
    )
    brand = models.ForeignKey(
        "catalog.Brand",
        on_delete=models.PROTECT,
        related_name="promotion_offer_scopes",
    )
    mode = models.CharField(
        max_length=8,
        choices=ScopeMode.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("offer", "brand"),
                name="promo_offer_brand_unique",
            ),
        ]

    def __str__(self):
        return f"{self.offer} - {self.brand} - {self.mode}"


class OfferSeasonScope(UUIDTimeStampedModel):
    offer = models.ForeignKey(
        CampaignOffer,
        on_delete=models.CASCADE,
        related_name="season_scopes",
    )
    season = models.ForeignKey(
        "catalog.Season",
        on_delete=models.PROTECT,
        related_name="promotion_offer_scopes",
    )
    mode = models.CharField(
        max_length=8,
        choices=ScopeMode.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("offer", "season"),
                name="promo_offer_season_unique",
            ),
        ]

    def __str__(self):
        return f"{self.offer} - {self.season} - {self.mode}"

class OfferSupplierScope(UUIDTimeStampedModel):
    offer = models.ForeignKey(
        CampaignOffer,
        on_delete=models.CASCADE,
        related_name="supplier_scopes",
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="promotion_offer_scopes",
    )
    mode = models.CharField(
        max_length=8,
        choices=ScopeMode.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("offer", "supplier"),
                name="promo_offer_supplier_unique",
            ),
        ]

    def __str__(self):
        return f"{self.offer} - {self.supplier} - {self.mode}"


class OfferProductScope(UUIDTimeStampedModel):
    offer = models.ForeignKey(
        CampaignOffer,
        on_delete=models.CASCADE,
        related_name="product_scopes",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="promotion_offer_scopes",
    )
    mode = models.CharField(
        max_length=8,
        choices=ScopeMode.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("offer", "product"),
                name="promo_offer_product_unique",
            ),
        ]

    def __str__(self):
        return f"{self.offer} - {self.product} - {self.mode}"


class OfferVariantScope(UUIDTimeStampedModel):
    offer = models.ForeignKey(
        CampaignOffer,
        on_delete=models.CASCADE,
        related_name="variant_scopes",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="promotion_offer_scopes",
    )
    mode = models.CharField(
        max_length=8,
        choices=ScopeMode.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("offer", "variant"),
                name="promo_offer_variant_unique",
            ),
        ]

    def __str__(self):
        return f"{self.offer} - {self.variant} - {self.mode}"

class SalePromotionApplication(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Applicata"
        REMOVED = "REMOVED", "Rimossa"

    sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.PROTECT,
        related_name="promotion_applications",
    )
    activation = models.ForeignKey(
        PromotionCampaignActivation,
        on_delete=models.PROTECT,
        related_name="sale_applications",
    )
    offer = models.ForeignKey(
        CampaignOffer,
        on_delete=models.PROTECT,
        related_name="sale_applications",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.APPLIED,
    )
    campaign_code_snapshot = models.CharField(max_length=48)
    campaign_name_snapshot = models.CharField(max_length=160)
    campaign_type_snapshot = models.CharField(max_length=16)
    offer_code_snapshot = models.CharField(max_length=48)
    offer_name_snapshot = models.CharField(max_length=160)
    rule_code_snapshot = models.CharField(max_length=48)
    rule_name_snapshot = models.CharField(max_length=160)
    rule_type_snapshot = models.CharField(max_length=32)
    rule_parameters_snapshot = models.JSONField(default=dict)
    scope_snapshot = models.JSONField(default=dict)
    total_discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="applied_sale_promotions",
    )
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="removed_sale_promotions",
    )
    removal_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("applied_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(total_discount_amount__gte=0),
                name="promo_application_discount_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(removed_at__isnull=True)
                    | Q(removed_at__gte=F("applied_at"))
                ),
                name="promo_application_dates_valid",
            ),
        ]

    def __str__(self):
        return (
            f"{self.sale} - {self.offer_name_snapshot} "
            f"({self.status})"
        )

class SalePromotionAllocation(UUIDTimeStampedModel):
    application = models.ForeignKey(
        SalePromotionApplication,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    sale_line = models.ForeignKey(
        "sales.SaleLine",
        on_delete=models.PROTECT,
        related_name="promotion_allocations",
    )
    sku_snapshot = models.CharField(max_length=64)
    product_code_snapshot = models.CharField(max_length=48)
    product_name_snapshot = models.CharField(max_length=160)
    category_code_snapshot = models.CharField(max_length=48)
    category_name_snapshot = models.CharField(max_length=120)
    brand_code_snapshot = models.CharField(max_length=48, blank=True)
    brand_name_snapshot = models.CharField(max_length=120, blank=True)
    season_code_snapshot = models.CharField(max_length=48, blank=True)
    season_name_snapshot = models.CharField(max_length=120, blank=True)
    supplier_codes_snapshot = models.JSONField(default=list)
    group_number = models.PositiveIntegerField(default=1)
    quantity_in_group = models.PositiveIntegerField()
    discounted_quantity = models.PositiveIntegerField(default=0)
    original_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    final_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    class Meta:
        ordering = (
            "application",
            "group_number",
            "created_at",
        )
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "application",
                    "sale_line",
                    "group_number",
                ),
                name="promo_allocation_line_group_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(quantity_in_group__gt=0)
                    & Q(discounted_quantity__gte=0)
                    & Q(
                        discounted_quantity__lte=F(
                            "quantity_in_group"
                        )
                    )
                ),
                name="promo_allocation_quantities_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(original_amount__gte=0)
                    & Q(final_amount__gte=0)
                    & Q(discount_amount__gte=0)
                    & Q(final_amount__lte=F("original_amount"))
                ),
                name="promo_allocation_amounts_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    discount_amount=(
                        F("original_amount") - F("final_amount")
                    )
                ),
                name="promo_allocation_difference_valid",
            ),
        ]

    def __str__(self):
        return (
            f"{self.application} - gruppo {self.group_number} - "
            f"{self.sale_line}"
        )
