from django.contrib import admin

from .models import (
    GiftList,
    GiftListContribution,
    GiftListItem,
    GiftListItemPurchase,
    ReservedStockSaleAuthorization,
)


class GiftListItemInline(admin.TabularInline):
    model = GiftListItem
    extra = 0
    autocomplete_fields = ("variant",)
    readonly_fields = ("purchased_quantity", "created_at", "updated_at")


class GiftListContributionInline(admin.TabularInline):
    model = GiftListContribution
    extra = 0
    readonly_fields = (
        "contributor_first_name", "contributor_last_name", "amount",
        "payment_method", "occurred_at", "recorded_by", "notes",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GiftList)
class GiftListAdmin(admin.ModelAdmin):
    list_display = (
        "code", "title", "list_type", "mode", "status",
        "beneficiary_last_name", "beneficiary_first_name", "event_date",
    )
    list_filter = ("list_type", "mode", "status", "event_date")
    search_fields = (
        "code", "title", "beneficiary_first_name",
        "beneficiary_last_name", "contact_phone", "contact_email",
    )
    autocomplete_fields = ("customer",)
    readonly_fields = (
        "generated_voucher", "closed_at", "closed_by", "cancelled_at",
        "cancelled_by", "created_at", "updated_at",
    )
    inlines = (GiftListItemInline, GiftListContributionInline)


@admin.register(GiftListItem)
class GiftListItemAdmin(admin.ModelAdmin):
    list_display = (
        "gift_list", "variant", "requested_quantity",
        "reserved_quantity", "purchased_quantity",
    )
    list_filter = ("gift_list__status",)
    search_fields = ("gift_list__code", "variant__sku")
    autocomplete_fields = ("gift_list", "variant")


@admin.register(GiftListContribution)
class GiftListContributionAdmin(admin.ModelAdmin):
    list_display = (
        "gift_list", "contributor_last_name", "contributor_first_name",
        "amount", "payment_method", "occurred_at",
    )
    list_filter = ("payment_method", "occurred_at")
    search_fields = (
        "gift_list__code", "contributor_first_name", "contributor_last_name",
    )
    readonly_fields = tuple(
        field.name for field in GiftListContribution._meta.fields
    )


@admin.register(GiftListItemPurchase)
class GiftListItemPurchaseAdmin(admin.ModelAdmin):
    list_display = ("item", "sale_line", "quantity", "sold_at")
    search_fields = ("item__gift_list__code", "item__variant__sku")
    readonly_fields = tuple(
        field.name for field in GiftListItemPurchase._meta.fields
    )


@admin.register(ReservedStockSaleAuthorization)
class ReservedStockSaleAuthorizationAdmin(admin.ModelAdmin):
    list_display = (
        "sale", "variant", "requested_sale_quantity",
        "reserved_quantity_snapshot", "authorized_at", "authorized_by",
    )
    search_fields = ("variant__sku", "reason")
    readonly_fields = tuple(
        field.name for field in ReservedStockSaleAuthorization._meta.fields
    )
