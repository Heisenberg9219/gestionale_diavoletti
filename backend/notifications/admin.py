from django.contrib import admin

from .models import Notification, NotificationDelivery, NotificationResolution


class NotificationDeliveryInline(admin.TabularInline):
    model = NotificationDelivery
    extra = 0
    can_delete = False
    readonly_fields = (
        "user", "matched_role_codes", "delivered_at", "read_at",
        "archived_at", "created_at", "updated_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at", "notification_type", "priority", "title", "status",
    )
    list_filter = ("notification_type", "priority", "status", "occurred_at")
    search_fields = ("title", "message", "deduplication_key", "source_type")
    readonly_fields = (
        "status", "resolved_at", "resolved_by", "resolution_notes",
        "created_at", "updated_at",
    )
    inlines = (NotificationDeliveryInline,)

    def get_readonly_fields(self, request, obj=None):
        if obj is None or obj.status == Notification.Status.ACTIVE:
            return self.readonly_fields
        return tuple(field.name for field in Notification._meta.fields)


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "notification", "user", "delivered_at", "read_at", "archived_at",
    )
    list_filter = ("delivered_at", "read_at", "archived_at")
    search_fields = ("notification__title", "user__email")
    readonly_fields = tuple(
        field.name for field in NotificationDelivery._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationResolution)
class NotificationResolutionAdmin(admin.ModelAdmin):
    list_display = ("notification", "resolved_at", "resolved_by")
    readonly_fields = tuple(
        field.name for field in NotificationResolution._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
