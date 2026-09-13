from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class LoyaltyEarningRule(UUIDTimeStampedModel):
    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    spend_block_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("10.00"),
    )
    points_per_block = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(
                condition=Q(spend_block_amount__gt=0),
                name="loyalty_spend_block_positive",
            ),
            models.CheckConstraint(
                condition=Q(points_per_block__gt=0),
                name="loyalty_points_per_block_positive",
            ),
        ]

    def __str__(self):
        return (
            f"{self.name}: {self.points_per_block} punti "
            f"ogni {self.spend_block_amount}"
        )


class LoyaltyEarningActivation(UUIDTimeStampedModel):
    rule = models.ForeignKey(
        LoyaltyEarningRule,
        on_delete=models.PROTECT,
        related_name="activations",
    )
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    singleton_key = models.BooleanField(
        default=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_loyalty_earning_activations",
    )

    class Meta:
        ordering = ("-valid_from",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(valid_until__isnull=True)
                    | Q(valid_until__gt=F("valid_from"))
                ),
                name="loyalty_activation_dates_valid",
            ),
            models.UniqueConstraint(
                fields=("singleton_key",),
                condition=Q(valid_until__isnull=True),
                name="loyalty_one_open_earning_activation",
            ),
        ]

    def __str__(self):
        return f"{self.rule.name} dal {self.valid_from}"

class LoyaltyPointMovement(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        EARNED = "EARNED", "Punti guadagnati"
        RETURN_REVERSAL = "RETURN_REVERSAL", "Storno per reso"
        REWARD_REDEMPTION = "REWARD_REDEMPTION", "Riscatto premio"
        MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT", "Rettifica manuale"
        EXPIRATION = "EXPIRATION", "Scadenza punti"

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="loyalty_point_movements",
    )
    points_delta = models.IntegerField()
    movement_type = models.CharField(
        max_length=24,
        choices=Type.choices,
    )
    earning_activation = models.ForeignKey(
        LoyaltyEarningActivation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="point_movements",
    )
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_loyalty_point_movements",
    )

    class Meta:
        ordering = ("-occurred_at", "-created_at")
        indexes = [
            models.Index(
                fields=("customer", "occurred_at"),
                name="loyalty_cust_points_date_idx",
            ),
            models.Index(
                fields=("source_type", "source_id"),
                name="loyalty_points_source_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(points_delta=0),
                name="loyalty_points_delta_non_zero",
            ),
        ]

    def __str__(self):
        return (
            f"{self.customer.customer_code}: "
            f"{self.points_delta} punti"
        )

class LoyaltyRewardDefinition(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        FIXED_AMOUNT_DISCOUNT = (
            "FIXED_AMOUNT_DISCOUNT",
            "Buono sconto a importo fisso",
        )
        PERCENTAGE_DISCOUNT = (
            "PERCENTAGE_DISCOUNT",
            "Sconto percentuale",
        )

    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    reward_type = models.CharField(
        max_length=32,
        choices=Type.choices,
    )
    points_cost = models.PositiveIntegerField()
    fixed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    minimum_purchase_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    validity_days = models.PositiveSmallIntegerField(default=180)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("points_cost", "name")
        constraints = [
            models.CheckConstraint(
                condition=Q(points_cost__gt=0),
                name="loyalty_reward_points_cost_positive",
            ),
            models.CheckConstraint(
                condition=Q(minimum_purchase_amount__gte=0),
                name="loyalty_reward_min_purchase_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(validity_days__gt=0),
                name="loyalty_reward_validity_days_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        reward_type="FIXED_AMOUNT_DISCOUNT",
                        fixed_amount__gt=0,
                        percentage__isnull=True,
                    )
                    | Q(
                        reward_type="PERCENTAGE_DISCOUNT",
                        fixed_amount__isnull=True,
                        percentage__gt=0,
                        percentage__lte=100,
                    )
                ),
                name="loyalty_reward_definition_value_valid",
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.points_cost} punti"

class IssuedLoyaltyReward(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Attivo"
        USED = "USED", "Utilizzato"
        EXPIRED = "EXPIRED", "Scaduto"
        CANCELLED = "CANCELLED", "Annullato"

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="issued_loyalty_rewards",
    )
    definition = models.ForeignKey(
        LoyaltyRewardDefinition,
        on_delete=models.PROTECT,
        related_name="issued_rewards",
    )
    code = models.CharField(max_length=64, unique=True)
    reward_type = models.CharField(
        max_length=32,
        choices=LoyaltyRewardDefinition.Type.choices,
    )
    points_spent = models.PositiveIntegerField()
    fixed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    remaining_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    minimum_purchase_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    point_movement = models.OneToOneField(
        LoyaltyPointMovement,
        on_delete=models.PROTECT,
        related_name="issued_reward",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_loyalty_rewards",
    )

    class Meta:
        ordering = ("-issued_at",)
        indexes = [
            models.Index(
                fields=("customer", "status", "expires_at"),
                name="loyalty_reward_customer_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(points_spent__gt=0),
                name="loyalty_issued_points_positive",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("issued_at")),
                name="loyalty_issued_dates_valid",
            ),
            models.CheckConstraint(
                condition=Q(minimum_purchase_amount__gte=0),
                name="loyalty_issued_min_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        reward_type="FIXED_AMOUNT_DISCOUNT",
                        fixed_amount__gt=0,
                        remaining_amount__gte=0,
                        remaining_amount__lte=F("fixed_amount"),
                        percentage__isnull=True,
                    )
                    | Q(
                        reward_type="PERCENTAGE_DISCOUNT",
                        fixed_amount__isnull=True,
                        remaining_amount__isnull=True,
                        percentage__gt=0,
                        percentage__lte=100,
                    )
                ),
                name="loyalty_issued_value_valid",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.customer.full_name}"


class LoyaltyRewardRedemption(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Applicato"
        CANCELLED = "CANCELLED", "Annullato"

    reward = models.ForeignKey(IssuedLoyaltyReward, on_delete=models.PROTECT, related_name="redemptions")
    sale = models.ForeignKey("sales.Sale", on_delete=models.PROTECT, related_name="loyalty_reward_redemptions")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.APPLIED)
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="applied_loyalty_reward_redemptions")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="cancelled_loyalty_reward_redemptions")
    cancellation_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("reward", "sale"), name="loyalty_reward_sale_unique"),
            models.CheckConstraint(condition=Q(discount_amount__gt=0), name="loyalty_reward_redemption_amount_positive"),
            models.CheckConstraint(condition=(Q(status="APPLIED", cancelled_at__isnull=True, cancelled_by__isnull=True, cancellation_reason="") | Q(status="CANCELLED", cancelled_at__isnull=False, cancelled_by__isnull=False, cancellation_reason__gt="")), name="loyalty_reward_redemption_audit"),
        ]
