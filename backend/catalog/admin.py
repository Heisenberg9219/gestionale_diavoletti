from django.contrib import admin

from .models import (
    Brand,
    Category,
    Color,
    Product,
    ProductBarcode,
    ProductVariant,
    Season,
    Size,
    SizeScale,
)

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "archived_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "parent",
        "display_order",
        "is_active",
        "archived_at",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    autocomplete_fields = ("parent",)
    ordering = ("display_order", "name")


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "year",
        "season_type",
        "start_date",
        "end_date",
        "is_active",
    )
    list_filter = ("season_type", "year", "is_active")
    search_fields = ("code", "name")
    ordering = ("-year", "season_type")


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "color_family",
        "hex_color",
        "display_order",
        "is_active",
    )
    list_filter = ("color_family", "is_active")
    search_fields = ("code", "name", "color_family")
    ordering = ("display_order", "name")


@admin.register(SizeScale)
class SizeScaleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "scale_type", "is_active", "archived_at")
    list_filter = ("scale_type", "is_active")
    search_fields = ("code", "name")
    ordering = ("name",)


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "label",
        "size_scale",
        "min_age_months",
        "max_age_months",
        "display_order",
        "is_active",
    )
    list_filter = ("size_scale", "is_active")
    search_fields = (
        "code",
        "label",
        "size_scale__code",
        "size_scale__name",
    )
    autocomplete_fields = ("size_scale",)
    ordering = ("size_scale", "display_order", "label")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "brand",
        "category",
        "season",
        "tax_rate",
        "is_active",
        "archived_at",
    )
    list_filter = ("is_active", "brand", "category", "season", "tax_rate")
    search_fields = ("code", "name", "description")
    autocomplete_fields = ("brand", "category", "season")
    list_select_related = ("brand", "category", "season", "tax_rate")
    ordering = ("name",)


class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 0
    fields = (
        "code",
        "barcode_type",
        "source",
        "is_primary",
        "is_active",
    )


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "product",
        "color",
        "size",
        "is_active",
        "archived_at",
    )
    list_filter = ("is_active", "color", "size__size_scale")
    search_fields = (
        "sku",
        "product__code",
        "product__name",
        "barcodes__code",
    )
    autocomplete_fields = ("product", "color", "size")
    list_select_related = ("product", "color", "size", "size__size_scale")
    ordering = ("product", "size", "color")
    inlines = (ProductBarcodeInline,)


@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "variant",
        "barcode_type",
        "source",
        "is_primary",
        "is_active",
    )
    list_filter = ("barcode_type", "source", "is_primary", "is_active")
    search_fields = (
        "code",
        "variant__sku",
        "variant__product__code",
        "variant__product__name",
    )
    autocomplete_fields = ("variant",)
    list_select_related = ("variant", "variant__product")
    ordering = ("variant", "-is_primary", "code")    