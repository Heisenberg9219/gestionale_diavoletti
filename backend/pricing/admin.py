from django.contrib import admin

from .models import VariantSalePrice


@admin.register(VariantSalePrice)
class VariantSalePriceAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "amount",
        "valid_from",
        "valid_until",
        "is_current",
        "source",
        "created_by",
    )
    list_filter = ("source", "valid_from", "valid_until")
    search_fields = (
        "variant__sku",
        "variant__product__code",
        "variant__product__name",
    )
    autocomplete_fields = ("variant",)
    list_select_related = (
        "variant",
        "variant__product",
        "created_by",
    )
    readonly_fields = ("created_by", "created_at", "updated_at")
    ordering = ("variant", "-valid_from")
    date_hierarchy = "valid_from"

    @admin.display(boolean=True, description="Attuale")
    def is_current(self, obj):
        return obj.valid_until is None

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return (
                "variant",
                "amount",
                "valid_from",
                "source",
                "notes",
                "created_by",
                "created_at",
                "updated_at",
            )
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False