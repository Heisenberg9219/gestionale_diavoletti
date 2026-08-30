from django.contrib import admin

from .models import Supplier, SupplierVariant


class SupplierVariantInline(admin.TabularInline):
    model = SupplierVariant
    extra = 0
    autocomplete_fields = ("variant",)
    fields = (
        "variant",
        "supplier_product_code",
        "is_preferred",
        "minimum_order_quantity",
        "lead_time_days",
        "is_active",
    )


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "business_name",
        "vat_number",
        "city",
        "phone",
        "email",
        "is_active",
        "archived_at",
    )
    list_filter = ("is_active", "country_code", "province")
    search_fields = (
        "code",
        "business_name",
        "vat_number",
        "tax_code",
        "email",
        "phone",
    )
    ordering = ("business_name",)
    inlines = (SupplierVariantInline,)


@admin.register(SupplierVariant)
class SupplierVariantAdmin(admin.ModelAdmin):
    list_display = (
        "supplier",
        "variant",
        "supplier_product_code",
        "is_preferred",
        "minimum_order_quantity",
        "lead_time_days",
        "is_active",
    )
    list_filter = ("is_preferred", "is_active", "supplier")
    search_fields = (
        "supplier__code",
        "supplier__business_name",
        "variant__sku",
        "variant__product__code",
        "variant__product__name",
        "supplier_product_code",
    )
    autocomplete_fields = ("supplier", "variant")
    list_select_related = (
        "supplier",
        "variant",
        "variant__product",
    )
    ordering = ("supplier", "variant")