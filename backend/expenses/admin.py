from django.contrib import admin

from .models import (
    Expense,
    ExpenseAttachment,
    ExpenseCategory,
    ExpensePayment,
    ExpenseStatusChange,
)


class ExpensePaymentInline(admin.TabularInline):
    model = ExpensePayment
    extra = 0
    can_delete = False
    readonly_fields = (
        "amount", "payment_method", "paid_at", "reference",
        "notes", "recorded_by", "created_at", "updated_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


class ExpenseAttachmentInline(admin.TabularInline):
    model = ExpenseAttachment
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "parent", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    autocomplete_fields = ("parent",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "document_date", "description", "category", "supplier",
        "total_amount", "paid_amount", "status", "due_date",
    )
    list_filter = ("status", "category", "document_date", "due_date")
    search_fields = (
        "description", "document_number", "supplier__business_name",
    )
    autocomplete_fields = ("category", "supplier")
    readonly_fields = (
        "paid_amount", "status", "cancelled_at", "cancelled_by",
        "cancellation_reason", "created_at", "updated_at",
    )
    inlines = (ExpensePaymentInline, ExpenseAttachmentInline)


@admin.register(ExpensePayment)
class ExpensePaymentAdmin(admin.ModelAdmin):
    list_display = ("expense", "amount", "payment_method", "paid_at")
    list_filter = ("payment_method", "paid_at")
    search_fields = ("expense__description", "reference")
    readonly_fields = tuple(field.name for field in ExpensePayment._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExpenseAttachment)
class ExpenseAttachmentAdmin(admin.ModelAdmin):
    list_display = ("expense", "original_name", "uploaded_by", "created_at")
    search_fields = ("expense__description", "original_name")


@admin.register(ExpenseStatusChange)
class ExpenseStatusChangeAdmin(admin.ModelAdmin):
    list_display = (
        "expense", "previous_status", "new_status", "changed_by", "created_at",
    )
    list_filter = ("previous_status", "new_status")
    readonly_fields = tuple(
        field.name for field in ExpenseStatusChange._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
