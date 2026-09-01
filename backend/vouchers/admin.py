from django.contrib import admin

from .models import (
    ExpiredVoucherAuthorization,
    Voucher,
    VoucherExpiryChange,
    VoucherMovement,
)


class ReadOnlyAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class VoucherMovementInline(admin.TabularInline):
    model = VoucherMovement
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "occurred_at",
        "movement_type",
        "amount_delta",
        "balance_after",
        "source_type",
        "source_id",
        "created_by",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Voucher)
class VoucherAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "voucher_type",
        "status",
        "current_balance",
        "holder_last_name",
        "holder_first_name",
        "expires_at",
    )
    list_filter = ("voucher_type", "status", "expires_at")
    search_fields = (
        "code",
        "holder_first_name",
        "holder_last_name",
        "source_type",
    )
    readonly_fields = tuple(
        field.name for field in Voucher._meta.fields
    )
    inlines = (VoucherMovementInline,)


@admin.register(VoucherMovement)
class VoucherMovementAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "voucher",
        "movement_type",
        "amount_delta",
        "balance_after",
        "occurred_at",
    )
    list_filter = ("movement_type", "occurred_at")
    search_fields = ("voucher__code", "source_type", "notes")
    readonly_fields = tuple(
        field.name for field in VoucherMovement._meta.fields
    )


@admin.register(VoucherExpiryChange)
class VoucherExpiryChangeAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "voucher",
        "previous_expires_at",
        "new_expires_at",
        "changed_by",
    )
    search_fields = ("voucher__code", "reason")
    readonly_fields = tuple(
        field.name for field in VoucherExpiryChange._meta.fields
    )


@admin.register(ExpiredVoucherAuthorization)
class ExpiredVoucherAuthorizationAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "voucher",
        "sale",
        "expires_at_snapshot",
        "authorized_at",
        "authorized_by",
    )
    search_fields = ("voucher__code", "reason")
    readonly_fields = tuple(
        field.name for field in ExpiredVoucherAuthorization._meta.fields
    )
