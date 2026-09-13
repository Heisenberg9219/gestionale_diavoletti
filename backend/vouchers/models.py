from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class Voucher(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        GIFT_CARD = "GIFT_CARD", "Buono regalo"
        GIFT_LIST = "GIFT_LIST", "Buono lista"
        RETURN_CREDIT = "RETURN_CREDIT", "Buono reso"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Attivo"
        EXHAUSTED = "EXHAUSTED", "Esaurito"
        CANCELLED = "CANCELLED", "Annullato"

    code = models.CharField(max_length=64, unique=True)
    voucher_type = models.CharField(max_length=24, choices=Type.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    initial_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2)
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    holder_first_name = models.CharField(max_length=120, blank=True)
    holder_last_name = models.CharField(max_length=120, blank=True)
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_vouchers",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_vouchers",
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    notifications_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ("-issued_at",)
        indexes = [
            models.Index(
                fields=("holder_last_name", "holder_first_name"),
                name="voucher_holder_name_idx",
            ),
            models.Index(
                fields=("source_type", "source_id"),
                name="voucher_source_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(initial_amount__gt=0),
                name="voucher_initial_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(current_balance__gte=0)
                    & Q(current_balance__lte=F("initial_amount"))
                ),
                name="voucher_balance_valid",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("issued_at")),
                name="voucher_expiry_valid",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="EXHAUSTED")
                    | Q(current_balance=Decimal("0.00"))
                ),
                name="voucher_exhausted_balance_zero",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="ACTIVE")
                    | Q(current_balance__gt=Decimal("0.00"))
                ),
                name="voucher_active_balance_positive",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.current_balance}"


class VoucherMovement(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        ISSUE = "ISSUE", "Emissione"
        REDEMPTION = "REDEMPTION", "Utilizzo"
        ADJUSTMENT = "ADJUSTMENT", "Rettifica"
        CANCELLATION = "CANCELLATION", "Annullamento"

    voucher = models.ForeignKey(
        Voucher,
        on_delete=models.PROTECT,
        related_name="movements",
    )
    movement_type = models.CharField(max_length=16, choices=Type.choices)
    amount_delta = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    occurred_at = models.DateTimeField(default=timezone.now)
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_voucher_movements",
    )

    class Meta:
        ordering = ("occurred_at", "created_at")
        indexes = [
            models.Index(
                fields=("voucher", "occurred_at"),
                name="voucher_move_date_idx",
            ),
            models.Index(
                fields=("source_type", "source_id"),
                name="voucher_move_source_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(amount_delta=0),
                name="voucher_movement_non_zero",
            ),
            models.CheckConstraint(
                condition=Q(balance_after__gte=0),
                name="voucher_movement_balance_non_negative",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("I movimenti dei buoni sono immutabili.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("I movimenti dei buoni sono immutabili.")

    def __str__(self):
        return f"{self.voucher.code}: {self.amount_delta}"


class VoucherExpiryChange(UUIDTimeStampedModel):
    voucher = models.ForeignKey(
        Voucher,
        on_delete=models.PROTECT,
        related_name="expiry_changes",
    )
    previous_expires_at = models.DateTimeField()
    new_expires_at = models.DateTimeField()
    reason = models.CharField(max_length=255)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="changed_voucher_expiries",
    )

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=~Q(new_expires_at=F("previous_expires_at")),
                name="voucher_expiry_change_required",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Le modifiche di scadenza sono immutabili.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Le modifiche di scadenza sono immutabili.")

    def __str__(self):
        return f"{self.voucher.code}: {self.new_expires_at}"


class ExpiredVoucherAuthorization(UUIDTimeStampedModel):
    voucher = models.ForeignKey(
        Voucher,
        on_delete=models.PROTECT,
        related_name="expired_use_authorizations",
    )
    sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.PROTECT,
        related_name="expired_voucher_authorizations",
    )
    expires_at_snapshot = models.DateTimeField()
    reason = models.CharField(max_length=255)
    authorized_at = models.DateTimeField(default=timezone.now)
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authorized_expired_vouchers",
    )

    class Meta:
        ordering = ("-authorized_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("voucher", "sale"),
                name="voucher_expired_auth_sale_unique",
            ),
        ]

    def __str__(self):
        return f"{self.voucher.code} - {self.sale}"
