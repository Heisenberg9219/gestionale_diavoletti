from django.contrib import admin

from .models import ReorderItem, ReorderItemChange, ReorderNotificationLink


class ReorderItemChangeInline(admin.TabularInline):
    model = ReorderItemChange
    extra = 0
    can_delete = False
    readonly_fields = (
        "previous_quantity", "new_quantity", "previous_supplier",
        "new_supplier", "changed_by", "created_at", "updated_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ReorderItem)
class ReorderItemAdmin(admin.ModelAdmin):
    list_display = (
        "variant", "location", "supplier", "requested_quantity",
        "status", "created_at",
    )
    list_filter = ("status", "supplier", "location")
    search_fields = (
        "variant__sku", "variant__product__name", "supplier__business_name",
    )
    autocomplete_fields = ("variant", "supplier")
    raw_id_fields = ("purchase_order_line",)
    readonly_fields = (
        "status", "purchase_order_line", "ordered_at", "ordered_by",
        "completed_at", "completed_by", "removed_at", "removed_by",
        "removal_reason", "created_at", "updated_at",
    )
    inlines = (ReorderItemChangeInline,)

    def get_readonly_fields(self, request, obj=None):
        if obj is None or obj.status == ReorderItem.Status.PENDING:
            return self.readonly_fields
        return tuple(field.name for field in ReorderItem._meta.fields)


@admin.register(ReorderNotificationLink)
class ReorderNotificationLinkAdmin(admin.ModelAdmin):
    list_display = ("reorder_item", "notification", "created_at")
    readonly_fields = tuple(
        field.name for field in ReorderNotificationLink._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReorderItemChange)
class ReorderItemChangeAdmin(admin.ModelAdmin):
    list_display = (
        "reorder_item", "previous_quantity", "new_quantity",
        "previous_supplier", "new_supplier", "changed_by", "created_at",
    )
    readonly_fields = tuple(
        field.name for field in ReorderItemChange._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
