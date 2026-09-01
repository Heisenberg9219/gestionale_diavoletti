from django.contrib import admin

from .models import (
    ExternalObjectMapping, ImportedOrder, IntegrationConnection, SyncEvent,
    WebhookEvent,
)


@admin.register(IntegrationConnection)
class IntegrationConnectionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "provider", "shop_domain", "is_active")
    list_filter = ("provider", "is_active")
    search_fields = ("code", "name", "shop_domain")
    autocomplete_fields = ("online_locations", "default_sale_location", "system_user")


@admin.register(ExternalObjectMapping)
class ExternalObjectMappingAdmin(admin.ModelAdmin):
    list_display = ("connection", "object_type", "internal_id", "external_id")
    list_filter = ("connection", "object_type")
    search_fields = ("external_id", "internal_id")


@admin.register(SyncEvent)
class SyncEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "connection", "status", "attempts", "available_at")
    list_filter = ("connection", "event_type", "status")
    search_fields = ("deduplication_key", "last_error")
    readonly_fields = tuple(field.name for field in SyncEvent._meta.fields)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("topic", "connection", "external_event_id", "status", "created_at")
    list_filter = ("connection", "topic", "status")
    search_fields = ("external_event_id", "topic", "error")
    readonly_fields = tuple(field.name for field in WebhookEvent._meta.fields)


@admin.register(ImportedOrder)
class ImportedOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "connection", "financial_status", "status", "sale")
    list_filter = ("connection", "status", "financial_status")
    search_fields = ("external_id", "order_number", "error")
    readonly_fields = tuple(field.name for field in ImportedOrder._meta.fields)
