from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import RoleMetadata, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = (
        "email",
        "first_name",
        "last_name",
        "status",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    list_filter = (
        "status",
        "is_staff",
        "is_superuser",
        "is_active",
        "groups",
    )
    search_fields = ("email", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Dati personali",
            {"fields": ("first_name", "last_name")},
        ),
        (
            "Stato gestionale",
            {"fields": ("status", "archived_at")},
        ),
        (
            "Permessi",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                )
            },
        ),
        (
            "Date",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                    "updated_at",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "status",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                ),
            },
        ),
    )

    readonly_fields = (
        "last_login",
        "date_joined",
        "updated_at",
    )
    filter_horizontal = ("groups",)


@admin.register(RoleMetadata)
class RoleMetadataAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "group",
        "is_system",
        "is_active",
    )
    list_filter = ("is_system", "is_active")
    search_fields = ("code", "group__name")
    readonly_fields = ("created_at", "updated_at")