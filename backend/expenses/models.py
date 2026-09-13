from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class ExpenseCategory(UUIDTimeStampedModel):
    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def clean(self):
        if self.parent_id and self.parent_id == self.id:
            raise ValidationError("Una categoria non può essere genitore di se stessa.")

    def __str__(self):
        return f"{self.code} - {self.name}"


class Expense(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Bozza"
        OPEN = "OPEN", "Da pagare"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Parzialmente pagata"
        PAID = "PAID", "Pagata"
        CANCELLED = "CANCELLED", "Annullata"

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="expenses",
    )
    location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="expenses",
    )
    description = models.CharField(max_length=255)
    document_number = models.CharField(max_length=120, blank=True)
    document_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    notifications_enabled = models.BooleanField(default=False)
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_expenses",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_expenses",
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-document_date", "-created_at")
        indexes = [
            models.Index(
                fields=("status", "due_date"),
                name="expense_status_due_idx",
            ),
            models.Index(
                fields=("category", "document_date"),
                name="expense_category_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(taxable_amount__gte=0)
                    & Q(tax_amount__gte=0)
                    & Q(total_amount__gt=0)
                    & Q(paid_amount__gte=0)
                    & Q(paid_amount__lte=F("total_amount"))
                ),
                name="expense_amounts_valid",
            ),
            models.CheckConstraint(
                condition=Q(total_amount=F("taxable_amount") + F("tax_amount")),
                name="expense_total_matches",
            ),
            models.CheckConstraint(
                condition=(Q(due_date__isnull=True) | Q(due_date__gte=F("document_date"))),
                name="expense_due_date_valid",
            ),
            models.CheckConstraint(
                condition=(~Q(status="PAID") | Q(paid_amount=F("total_amount"))),
                name="expense_paid_balance_valid",
            ),
            models.CheckConstraint(
                condition=(~Q(status="PARTIALLY_PAID") | Q(paid_amount__gt=0)),
                name="expense_partial_balance_pos",
            ),
        ]

    @property
    def outstanding_amount(self):
        return self.total_amount - self.paid_amount

    def __str__(self):
        return f"{self.document_date} - {self.description}"


class ExpensePayment(UUIDTimeStampedModel):
    class Method(models.TextChoices):
        CASH = "CASH", "Contanti"
        CARD = "CARD", "Carta"
        BANK_TRANSFER = "BANK_TRANSFER", "Bonifico"
        DIRECT_DEBIT = "DIRECT_DEBIT", "Addebito diretto"
        OTHER = "OTHER", "Altro"

    expense = models.ForeignKey(
        Expense,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=24, choices=Method.choices)
    paid_at = models.DateTimeField(default=timezone.now)
    reference = models.CharField(max_length=160, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_expense_payments",
    )

    class Meta:
        ordering = ("paid_at", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="expense_payment_amount_pos",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("I pagamenti delle spese sono immutabili.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("I pagamenti delle spese sono immutabili.")


class ExpenseAttachment(UUIDTimeStampedModel):
    expense = models.ForeignKey(
        Expense,
        on_delete=models.PROTECT,
        related_name="attachments",
    )
    file = models.FileField(upload_to="expenses/%Y/%m/")
    original_name = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_expense_attachments",
    )

    class Meta:
        ordering = ("created_at",)


class ExpenseStatusChange(UUIDTimeStampedModel):
    expense = models.ForeignKey(
        Expense,
        on_delete=models.PROTECT,
        related_name="status_changes",
    )
    previous_status = models.CharField(max_length=24, choices=Expense.Status.choices)
    new_status = models.CharField(max_length=24, choices=Expense.Status.choices)
    reason = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="changed_expense_statuses",
    )

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=~Q(previous_status=F("new_status")),
                name="expense_status_change_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Lo storico degli stati è immutabile.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Lo storico degli stati è immutabile.")
