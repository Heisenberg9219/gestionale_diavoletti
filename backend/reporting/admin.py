from django.contrib import admin

from .models import ReportDashboard, ReportExport, ReportSnapshot, ReportWidget


class OwnerOnlyAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.groups.filter(name="Titolare").exists()

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(ReportDashboard)
class ReportDashboardAdmin(OwnerOnlyAdmin):
    list_display = ("code", "name", "is_active", "updated_at", "updated_by")
    search_fields = ("code", "name")
    list_filter = ("is_active",)
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ReportWidget)
class ReportWidgetAdmin(OwnerOnlyAdmin):
    list_display = ("title", "dashboard", "metric", "visualization", "period", "group_by", "auto_refresh_daily")
    list_filter = ("dashboard", "metric", "visualization", "period", "auto_refresh_daily")
    search_fields = ("title", "dashboard__name")
    autocomplete_fields = ("dashboard",)
    readonly_fields = ("created_by", "updated_by", "last_refreshed_at", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ReportSnapshot)
class ReportSnapshotAdmin(OwnerOnlyAdmin):
    list_display = ("widget", "snapshot_date", "period_from", "period_to", "generated_by")
    list_filter = ("snapshot_date", "widget__dashboard")
    readonly_fields = tuple(field.name for field in ReportSnapshot._meta.fields)


@admin.register(ReportExport)
class ReportExportAdmin(OwnerOnlyAdmin):
    list_display = ("widget", "export_format", "status", "requested_by", "created_at", "completed_at")
    list_filter = ("export_format", "status")
    readonly_fields = tuple(field.name for field in ReportExport._meta.fields)
