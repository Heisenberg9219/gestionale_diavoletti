from django.contrib import admin

from .models import StockBalance, StockMovement, VariantInventoryCost


class ReadOnlyInventoryAdmin(admin.ModelAdmin):
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockBalance)
class StockBalanceAdmin(ReadOnlyInventoryAdmin):
    list_display = (
        "variant",
        "location",
        "quantity_on_hand",
        "updated_at",
    )
    list_filter = ("location",)
    search_fields = (
        "variant__sku",
        "variant__product__code",
        "variant__product__name",
        "location__code",
        "location__name",
    )
    list_select_related = (
        "variant",
        "variant__product",
        "location",
    )
    ordering = ("location", "variant")


@admin.register(VariantInventoryCost)
class VariantInventoryCostAdmin(ReadOnlyInventoryAdmin):
    list_display = (
        "variant",
        "weighted_average_unit_cost",
        "total_quantity",
        "inventory_value",
        "last_movement_at",
    )
    search_fields = (
        "variant__sku",
        "variant__product__code",
        "variant__product__name",
    )
    list_select_related = ("variant", "variant__product")
    ordering = ("variant",)


@admin.register(StockMovement)
class StockMovementAdmin(ReadOnlyInventoryAdmin):
    list_display = (
        "occurred_at",
        "variant",
        "location",
        "movement_type",
        "quantity_delta",
        "unit_cost",
        "reference_number",
        "created_by",
    )
    list_filter = ("movement_type", "location", "occurred_at")
    search_fields = (
        "variant__sku",
        "variant__product__code",
        "variant__product__name",
        "reference_number",
        "source_type",
    )
    list_select_related = (
        "variant",
        "variant__product",
        "location",
        "created_by",
    )
    ordering = ("-occurred_at", "-created_at")
    date_hierarchy = "occurred_at"