from django.contrib import admin

from .models import (
    BusinessDocument,
    DocumentAttachment,
    DocumentNumberSequence,
    DocumentStatusChange,
    DocumentType,
)


class DocumentAttachmentInline(admin.TabularInline):
    model = DocumentAttachment
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class DocumentStatusChangeInline(admin.TabularInline):
    model = DocumentStatusChange
    extra = 0
    can_delete = False
    readonly_fields = (
        "previous_status", "new_status", "reason", "changed_by", "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = (
        "code", "name", "direction", "requires_number",
        "automatic_numbering", "is_active",
    )
    list_filter = ("direction", "automatic_numbering", "is_active")
    search_fields = ("code", "name")


@admin.register(BusinessDocument)
class BusinessDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "document_date", "document_type", "number", "title",
        "direction", "status", "counterparty_name", "total_amount",
    )
    list_filter = ("document_type", "direction", "status", "document_date")
    search_fields = (
        "number", "title", "counterparty_name", "counterparty_vat_number",
        "counterparty_tax_code", "source_type",
    )
    autocomplete_fields = ("document_type",)
    readonly_fields = (
        "status", "registered_at", "issued_at", "cancelled_at",
        "cancelled_by", "cancellation_reason", "created_at", "updated_at",
    )
    inlines = (DocumentAttachmentInline, DocumentStatusChangeInline)

    def get_readonly_fields(self, request, obj=None):
        base_fields = self.readonly_fields
        if obj is None or obj.status == BusinessDocument.Status.DRAFT:
            return base_fields
        return tuple(field.name for field in BusinessDocument._meta.fields)


@admin.register(DocumentAttachment)
class DocumentAttachmentAdmin(admin.ModelAdmin):
    list_display = ("document", "original_name", "uploaded_by", "created_at")
    search_fields = ("document__number", "document__title", "original_name")


@admin.register(DocumentNumberSequence)
class DocumentNumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("document_type", "year", "last_number")
    readonly_fields = tuple(
        field.name for field in DocumentNumberSequence._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DocumentStatusChange)
class DocumentStatusChangeAdmin(admin.ModelAdmin):
    list_display = (
        "document", "previous_status", "new_status", "changed_by", "created_at",
    )
    list_filter = ("previous_status", "new_status")
    readonly_fields = tuple(
        field.name for field in DocumentStatusChange._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
