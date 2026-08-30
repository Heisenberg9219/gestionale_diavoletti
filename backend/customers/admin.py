from django.contrib import admin

from .models import (
    ConsentPurpose,
    Customer,
    CustomerChild,
    CustomerConsentEvent,
)


class CustomerChildInline(admin.TabularInline):
    model = CustomerChild
    extra = 0
    fields = (
        "first_name",
        "birth_date",
        "expected_birth_date",
        "gender",
        "is_active",
    )


class CustomerConsentEventInline(admin.TabularInline):
    model = CustomerConsentEvent
    extra = 0
    can_delete = False
    fields = (
        "purpose",
        "action",
        "notice_version",
        "occurred_at",
        "channel",
        "collected_by",
    )
    readonly_fields = fields
    ordering = ("-occurred_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "customer_code",
        "last_name",
        "first_name",
        "phone",
        "email",
        "city",
        "is_active",
        "archived_at",
    )
    list_filter = ("is_active", "province", "country_code")
    search_fields = (
        "customer_code",
        "first_name",
        "last_name",
        "phone",
        "email",
    )
    readonly_fields = ("created_by", "created_at", "updated_at")
    ordering = ("last_name", "first_name")
    inlines = (
        CustomerChildInline,
        CustomerConsentEventInline,
    )

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CustomerChild)
class CustomerChildAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "customer",
        "birth_date",
        "expected_birth_date",
        "gender",
        "is_active",
    )
    list_filter = ("gender", "is_active")
    search_fields = (
        "first_name",
        "customer__customer_code",
        "customer__first_name",
        "customer__last_name",
    )
    autocomplete_fields = ("customer",)
    list_select_related = ("customer",)
    ordering = ("customer", "first_name")


@admin.register(ConsentPurpose)
class ConsentPurposeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "notice_version",
        "requires_double_opt_in",
        "is_active",
    )
    list_filter = ("requires_double_opt_in", "is_active")
    search_fields = ("code", "name", "description")
    ordering = ("name",)


@admin.register(CustomerConsentEvent)
class CustomerConsentEventAdmin(admin.ModelAdmin):
    actions = None
    list_display = (
        "occurred_at",
        "customer",
        "purpose",
        "action",
        "channel",
        "notice_version",
        "collected_by",
    )
    list_filter = ("action", "channel", "purpose", "occurred_at")
    search_fields = (
        "customer__customer_code",
        "customer__first_name",
        "customer__last_name",
        "purpose__code",
    )
    list_select_related = (
        "customer",
        "purpose",
        "collected_by",
    )
    ordering = ("-occurred_at", "-created_at")
    date_hierarchy = "occurred_at"

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False