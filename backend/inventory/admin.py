from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import (
    InventoryCountLine,
    InventoryCountSession,
    StockBalance,
    StockMovement,
    VariantInventoryCost,
)
from .services import (
    cancel_inventory_count,
    confirm_inventory_count,
    record_inventory_count,
    start_inventory_count,
)


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


@admin.register(InventoryCountSession)
class InventoryCountSessionAdmin(admin.ModelAdmin):
    list_display = (
        "code", "name", "location", "scope", "status",
        "started_at", "confirmed_at", "created_by",
    )
    list_filter = ("status", "scope", "location", "confirmed_at")
    search_fields = ("code", "name", "notes")
    autocomplete_fields = (
        "location", "brands", "categories", "seasons", "products", "variants",
    )
    readonly_fields = (
        "status", "started_at", "confirmed_at", "confirmed_by",
        "cancelled_at", "cancelled_by", "created_at", "updated_at",
    )
    actions = ("start_selected", "confirm_selected", "cancel_selected")
    date_hierarchy = "created_at"

    def get_readonly_fields(self, request, obj=None):
        fields = list(self.readonly_fields)
        if obj and obj.status != InventoryCountSession.Status.DRAFT:
            fields.extend((
                "code", "name", "location", "scope", "notes",
                "brands", "categories", "seasons", "products", "variants",
            ))
        return tuple(fields)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Avvia gli inventari selezionati")
    def start_selected(self, request, queryset):
        self._run_action(
            request,
            queryset,
            lambda session: start_inventory_count(session=session),
        )

    @admin.action(description="Conferma gli inventari selezionati")
    def confirm_selected(self, request, queryset):
        self._run_action(
            request,
            queryset,
            lambda session: confirm_inventory_count(
                session=session,
                confirmed_by=request.user,
            ),
        )

    @admin.action(description="Annulla gli inventari selezionati")
    def cancel_selected(self, request, queryset):
        self._run_action(
            request,
            queryset,
            lambda session: cancel_inventory_count(
                session=session,
                cancelled_by=request.user,
            ),
        )

    def _run_action(self, request, queryset, operation):
        completed = 0
        for session in queryset:
            try:
                operation(session)
                completed += 1
            except ValidationError as exc:
                self.message_user(
                    request,
                    f"{session.code}: {'; '.join(exc.messages)}",
                    level="ERROR",
                )
        if completed:
            self.message_user(request, f"Sessioni elaborate: {completed}.")


@admin.register(InventoryCountLine)
class InventoryCountLineAdmin(admin.ModelAdmin):
    list_display = (
        "session", "variant", "expected_quantity", "counted_quantity",
        "difference_quantity", "unit_cost_snapshot", "difference_value",
    )
    list_filter = ("session__status", "session__location", "session")
    search_fields = (
        "session__code", "variant__sku", "variant__product__code",
        "variant__product__name",
    )
    list_select_related = ("session", "variant", "variant__product")
    autocomplete_fields = ("session", "variant")
    readonly_fields = (
        "session", "variant", "expected_quantity", "difference_quantity",
        "unit_cost_snapshot", "expected_value", "counted_value",
        "difference_value", "counted_at", "counted_by", "adjustment_movement",
        "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        fields = list(self.readonly_fields)
        if obj and obj.session.status != InventoryCountSession.Status.IN_PROGRESS:
            fields.extend(("counted_quantity", "notes"))
        return tuple(fields)

    def save_model(self, request, obj, form, change):
        if not change or "counted_quantity" not in form.changed_data:
            if "notes" in form.changed_data and obj.pk:
                record_inventory_count(
                    line=obj,
                    counted_quantity=obj.counted_quantity,
                    counted_by=request.user,
                    notes=obj.notes,
                )
            return
        record_inventory_count(
            line=obj,
            counted_quantity=obj.counted_quantity,
            counted_by=request.user,
            notes=obj.notes,
        )
