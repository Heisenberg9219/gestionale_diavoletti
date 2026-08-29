from django.contrib import admin

from .models import Location, ShopSettings, TaxRate


@admin.register(ShopSettings)
class ShopSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "shop_name",
        "currency_code",
        "default_markup",
        "return_credit_months",
    )
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return not ShopSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "type",
        "is_active",
    )
    list_filter = ("type", "is_active")
    search_fields = ("code", "name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TaxRate)
class TaxRateAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "percentage",
        "is_default",
        "is_active",
    )
    list_filter = ("is_default", "is_active")
    search_fields = ("code", "name")
    readonly_fields = ("created_at", "updated_at")