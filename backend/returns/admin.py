from django.contrib import admin

from .models import (
    CustomerReturn,
    CustomerReturnLine,
    CustomerReturnNumberSequence,
)


class CustomerReturnLineInline(admin.TabularInline):
    model = CustomerReturnLine
    extra = 0
    autocomplete_fields = ("original_sale_line",)
    readonly_fields = (
        "unit_refund_amount", "total_refund_amount",
        "sku_snapshot", "product_name_snapshot", "created_at", "updated_at",
    )


@admin.register(CustomerReturn)
class CustomerReturnAdmin(admin.ModelAdmin):
    list_display = (
        "number", "original_sale", "customer", "status",
        "total_refund_amount", "points_reversed", "created_at",
    )
    list_filter = ("status", "location", "created_at")
    search_fields = (
        "number", "original_sale__number", "customer__customer_code",
        "customer__first_name", "customer__last_name", "reason",
    )
    autocomplete_fields = ("original_sale", "customer")
    readonly_fields = (
        "number", "status", "total_refund_amount", "points_reversed",
        "return_voucher", "confirmed_at", "confirmed_by", "cancelled_at",
        "cancelled_by", "cancellation_reason", "created_at", "updated_at",
    )
    inlines = (CustomerReturnLineInline,)

    def get_readonly_fields(self, request, obj=None):
        if obj is None or obj.status == CustomerReturn.Status.DRAFT:
            return self.readonly_fields
        return tuple(field.name for field in CustomerReturn._meta.fields)


@admin.register(CustomerReturnLine)
class CustomerReturnLineAdmin(admin.ModelAdmin):
    list_display = (
        "customer_return", "sku_snapshot", "quantity", "restock",
        "total_refund_amount",
    )
    list_filter = ("restock", "customer_return__status")
    search_fields = ("customer_return__number", "sku_snapshot")
    readonly_fields = tuple(
        field.name for field in CustomerReturnLine._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomerReturnNumberSequence)
class CustomerReturnNumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("year", "last_number")
    readonly_fields = tuple(
        field.name for field in CustomerReturnNumberSequence._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
