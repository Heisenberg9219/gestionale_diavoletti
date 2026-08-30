from django.contrib import admin

from .models import (
    IssuedLoyaltyReward,
    LoyaltyEarningActivation,
    LoyaltyEarningRule,
    LoyaltyPointMovement,
    LoyaltyRewardDefinition,
)


class ReadOnlyLoyaltyAdmin(admin.ModelAdmin):
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoyaltyEarningRule)
class LoyaltyEarningRuleAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "spend_block_amount",
        "points_per_block",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("name",)


@admin.register(LoyaltyEarningActivation)
class LoyaltyEarningActivationAdmin(ReadOnlyLoyaltyAdmin):
    list_display = (
        "rule",
        "valid_from",
        "valid_until",
        "created_by",
    )
    list_filter = ("rule", "valid_from", "valid_until")
    search_fields = ("rule__code", "rule__name")
    list_select_related = ("rule", "created_by")
    ordering = ("-valid_from",)


@admin.register(LoyaltyPointMovement)
class LoyaltyPointMovementAdmin(ReadOnlyLoyaltyAdmin):
    list_display = (
        "occurred_at",
        "customer",
        "points_delta",
        "movement_type",
        "earning_activation",
        "source_type",
        "created_by",
    )
    list_filter = ("movement_type", "occurred_at")
    search_fields = (
        "customer__customer_code",
        "customer__first_name",
        "customer__last_name",
        "source_type",
    )
    list_select_related = (
        "customer",
        "earning_activation",
        "created_by",
    )
    ordering = ("-occurred_at", "-created_at")
    date_hierarchy = "occurred_at"


@admin.register(LoyaltyRewardDefinition)
class LoyaltyRewardDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "reward_type",
        "points_cost",
        "fixed_amount",
        "percentage",
        "validity_days",
        "is_active",
    )
    list_filter = ("reward_type", "is_active")
    search_fields = ("code", "name")
    ordering = ("points_cost", "name")


@admin.register(IssuedLoyaltyReward)
class IssuedLoyaltyRewardAdmin(ReadOnlyLoyaltyAdmin):
    list_display = (
        "code",
        "customer",
        "reward_type",
        "points_spent",
        "remaining_amount",
        "percentage",
        "issued_at",
        "expires_at",
        "status",
    )
    list_filter = ("reward_type", "status", "issued_at", "expires_at")
    search_fields = (
        "code",
        "customer__customer_code",
        "customer__first_name",
        "customer__last_name",
    )
    list_select_related = (
        "customer",
        "definition",
        "point_movement",
        "created_by",
    )
    ordering = ("-issued_at",)
    date_hierarchy = "issued_at"