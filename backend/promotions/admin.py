from django.contrib import admin

from .models import (
    CampaignOffer,
    OfferBrandScope,
    OfferCategoryScope,
    OfferProductScope,
    OfferSeasonScope,
    OfferSupplierScope,
    OfferVariantScope,
    PromotionCampaign,
    PromotionCampaignActivation,
    PromotionRule,
    SalePromotionAllocation,
    SalePromotionApplication,
)


class ScopeInline(admin.TabularInline):
    extra = 0


class OfferCategoryScopeInline(ScopeInline):
    model = OfferCategoryScope
    raw_id_fields = ("category",)


class OfferBrandScopeInline(ScopeInline):
    model = OfferBrandScope
    raw_id_fields = ("brand",)


class OfferSeasonScopeInline(ScopeInline):
    model = OfferSeasonScope
    raw_id_fields = ("season",)


class OfferSupplierScopeInline(ScopeInline):
    model = OfferSupplierScope
    raw_id_fields = ("supplier",)


class OfferProductScopeInline(ScopeInline):
    model = OfferProductScope
    raw_id_fields = ("product",)


class OfferVariantScopeInline(ScopeInline):
    model = OfferVariantScope
    raw_id_fields = ("variant",)


@admin.register(PromotionCampaign)
class PromotionCampaignAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "campaign_type", "is_active")
    list_filter = ("campaign_type", "is_active")
    search_fields = ("code", "name")
    raw_id_fields = ("created_by",)


@admin.register(PromotionRule)
class PromotionRuleAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "rule_type",
        "required_quantity",
        "repeatable",
        "is_active",
    )
    list_filter = (
        "rule_type",
        "repeatable",
        "grouping_mode",
        "target_selection",
        "is_active",
    )
    search_fields = ("code", "name")


@admin.register(CampaignOffer)
class CampaignOfferAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "campaign",
        "rule",
        "is_active",
        "sort_order",
    )
    list_filter = ("campaign", "is_active")
    search_fields = ("code", "name", "campaign__name", "rule__name")
    raw_id_fields = ("campaign", "rule", "created_by")
    inlines = (
        OfferCategoryScopeInline,
        OfferBrandScopeInline,
        OfferSeasonScopeInline,
        OfferSupplierScopeInline,
        OfferProductScopeInline,
        OfferVariantScopeInline,
    )


class ReadOnlyAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PromotionCampaignActivation)
class PromotionCampaignActivationAdmin(
    ReadOnlyAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "campaign",
        "activation_number",
        "status",
        "valid_from",
        "valid_until",
        "enabled_by",
    )
    list_filter = ("status", "campaign__campaign_type")
    search_fields = ("campaign__code", "campaign__name")
    date_hierarchy = "valid_from"


@admin.register(SalePromotionApplication)
class SalePromotionApplicationAdmin(
    ReadOnlyAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "sale",
        "activation",
        "offer_name_snapshot",
        "status",
        "total_discount_amount",
        "applied_at",
        "applied_by",
    )
    list_filter = ("status", "campaign_type_snapshot")
    search_fields = (
        "sale__number",
        "campaign_code_snapshot",
        "offer_code_snapshot",
        "rule_code_snapshot",
    )
    date_hierarchy = "applied_at"


@admin.register(SalePromotionAllocation)
class SalePromotionAllocationAdmin(
    ReadOnlyAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "application",
        "group_number",
        "sku_snapshot",
        "brand_name_snapshot",
        "quantity_in_group",
        "discounted_quantity",
        "discount_amount",
    )
    list_filter = (
        "application__activation",
        "brand_name_snapshot",
        "category_name_snapshot",
    )
    search_fields = (
        "sku_snapshot",
        "product_code_snapshot",
        "product_name_snapshot",
        "brand_name_snapshot",
        "category_name_snapshot",
    )
