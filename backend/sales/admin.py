from django.contrib import admin

from .models import (
    CashRegister,
    CashSession,
    Sale,
    SaleLine,
    SaleNumberSequence,
    SalePayment,
)


class ReadOnlyInlineMixin:
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


class SaleLineInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = SaleLine
    fields = (
        "variant",
        "quantity",
        "pricing_mode",
        "base_unit_price",
        "final_unit_price",
        "total_override_share",
        "net_amount",
        "tax_amount",
    )


class SalePaymentInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = SalePayment
    fields = (
        "method",
        "amount",
        "cash_received_amount",
        "cash_change_amount",
        "transaction_reference",
        "occurred_at",
    )


@admin.register(CashRegister)
class CashRegisterAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "location",
        "is_active",
    )
    list_filter = ("is_active", "location")
    search_fields = ("code", "name")
    autocomplete_fields = ("location",)


@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = (
        "cash_register",
        "status",
        "opened_at",
        "opened_by",
        "closed_at",
        "cash_difference",
    )
    list_filter = ("status", "cash_register")
    search_fields = (
        "cash_register__code",
        "cash_register__name",
        "opened_by__email",
    )
    date_hierarchy = "opened_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "number_or_open",
        "status",
        "channel",
        "location",
        "customer",
        "final_total_amount",
        "opened_at",
    )
    list_filter = ("status", "channel", "location")
    search_fields = (
        "number",
        "customer__customer_code",
        "customer__first_name",
        "customer__last_name",
    )
    date_hierarchy = "opened_at"
    inlines = (SaleLineInline, SalePaymentInline)

    @admin.display(description="Vendita", ordering="number")
    def number_or_open(self, obj):
        return obj.number or f"Aperta {obj.id}"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SaleLine)
class SaleLineAdmin(admin.ModelAdmin):
    list_display = (
        "sale",
        "sku_snapshot",
        "quantity",
        "pricing_mode",
        "net_amount",
        "tax_amount",
    )
    list_filter = ("pricing_mode",)
    search_fields = (
        "sale__number",
        "sku_snapshot",
        "product_name_snapshot",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SalePayment)
class SalePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "sale",
        "method",
        "amount",
        "occurred_at",
        "created_by",
    )
    list_filter = ("method",)
    search_fields = (
        "sale__number",
        "transaction_reference",
    )
    date_hierarchy = "occurred_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SaleNumberSequence)
class SaleNumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("year", "last_number", "updated_at")
    ordering = ("-year",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
