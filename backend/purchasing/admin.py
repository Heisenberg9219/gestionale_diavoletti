from django.contrib import admin

from .models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseCostAdjustment,
    PurchaseOrder,
    PurchaseOrderLine,
    SupplierInvoice,
    SupplierInvoiceLine,
    SupplierInvoiceReceipt,
)


class DraftOnlyInline:
    def has_add_permission(self, request, obj=None):
        return obj is None or obj.status == "DRAFT"

    def has_change_permission(self, request, obj=None):
        return obj is None or obj.status == "DRAFT"

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.status == "DRAFT"


class PurchaseOrderLineInline(
    DraftOnlyInline,
    admin.TabularInline,
):
    model = PurchaseOrderLine
    extra = 0
    autocomplete_fields = ("variant",)
    fields = (
        "variant",
        "supplier_product_code",
        "quantity_ordered",
        "expected_unit_cost",
        "notes",
    )


class GoodsReceiptLineInline(
    DraftOnlyInline,
    admin.TabularInline,
):
    model = GoodsReceiptLine
    extra = 0
    autocomplete_fields = ("variant",)
    raw_id_fields = ("purchase_order_line",)
    fields = (
        "variant",
        "purchase_order_line",
        "quantity_received",
        "unit_cost",
        "final_sale_price",
        "notes",
    )


class SupplierInvoiceReceiptInline(
    DraftOnlyInline,
    admin.TabularInline,
):
    model = SupplierInvoiceReceipt
    extra = 0
    autocomplete_fields = ("receipt",)


class SupplierInvoiceLineInline(
    DraftOnlyInline,
    admin.TabularInline,
):
    model = SupplierInvoiceLine
    extra = 0
    autocomplete_fields = ("variant",)
    raw_id_fields = ("receipt_line",)
    fields = (
        "variant",
        "receipt_line",
        "quantity_invoiced",
        "final_unit_cost",
        "tax_percentage",
        "taxable_amount",
        "tax_amount",
        "total_amount",
    )

class DraftDocumentAdmin(admin.ModelAdmin):
    actions = None
    system_readonly_fields = (
        "status",
        "created_by",
        "created_at",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.status != "DRAFT":
            return tuple(field.name for field in self.model._meta.fields)
        return self.system_readonly_fields

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.status == "DRAFT"

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(DraftDocumentAdmin):
    list_display = (
        "number",
        "supplier",
        "order_date",
        "expected_delivery_date",
        "status",
        "sent_at",
    )
    list_filter = ("status", "supplier", "order_date")
    search_fields = (
        "number",
        "supplier__code",
        "supplier__business_name",
    )
    autocomplete_fields = ("supplier",)
    list_select_related = ("supplier", "created_by", "sent_by")
    ordering = ("-order_date", "-created_at")
    date_hierarchy = "order_date"
    inlines = (PurchaseOrderLineInline,)
    system_readonly_fields = (
        "status",
        "created_by",
        "sent_at",
        "sent_by",
        "cancelled_at",
        "cancelled_by",
        "created_at",
        "updated_at",
    )


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(DraftDocumentAdmin):
    list_display = (
        "number",
        "supplier",
        "purchase_order",
        "destination_location",
        "received_at",
        "status",
        "confirmed_at",
    )
    list_filter = (
        "status",
        "supplier",
        "destination_location",
        "received_at",
    )
    search_fields = (
        "number",
        "delivery_note_number",
        "supplier__code",
        "supplier__business_name",
        "purchase_order__number",
    )
    autocomplete_fields = ("supplier", "purchase_order")
    list_select_related = (
        "supplier",
        "purchase_order",
        "destination_location",
        "created_by",
        "confirmed_by",
    )
    ordering = ("-received_at", "-created_at")
    date_hierarchy = "received_at"
    inlines = (GoodsReceiptLineInline,)
    system_readonly_fields = (
        "status",
        "created_by",
        "confirmed_at",
        "confirmed_by",
        "cancelled_at",
        "cancelled_by",
        "created_at",
        "updated_at",
    )


@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(DraftDocumentAdmin):
    list_display = (
        "invoice_number",
        "supplier",
        "invoice_date",
        "due_date",
        "total_amount",
        "status",
        "confirmed_at",
    )
    list_filter = ("status", "supplier", "invoice_date", "due_date")
    search_fields = (
        "invoice_number",
        "supplier__code",
        "supplier__business_name",
    )
    autocomplete_fields = ("supplier",)
    list_select_related = (
        "supplier",
        "created_by",
        "confirmed_by",
    )
    ordering = ("-invoice_date", "-created_at")
    date_hierarchy = "invoice_date"
    inlines = (
        SupplierInvoiceReceiptInline,
        SupplierInvoiceLineInline,
    )
    system_readonly_fields = (
        "status",
        "created_by",
        "confirmed_at",
        "confirmed_by",
        "cancelled_at",
        "cancelled_by",
        "created_at",
        "updated_at",
    )


@admin.register(PurchaseCostAdjustment)
class PurchaseCostAdjustmentAdmin(admin.ModelAdmin):
    actions = None
    list_display = (
        "created_at",
        "variant",
        "quantity_invoiced",
        "previous_unit_cost",
        "final_unit_cost",
        "inventory_value_delta",
        "sold_cost_delta",
    )
    search_fields = (
        "variant__sku",
        "variant__product__code",
        "variant__product__name",
        "invoice_line__invoice__invoice_number",
    )
    list_select_related = (
        "variant",
        "variant__product",
        "invoice_line",
        "invoice_line__invoice",
    )
    ordering = ("-created_at",)

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
