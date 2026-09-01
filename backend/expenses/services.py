from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Expense, ExpensePayment, ExpenseStatusChange


def _money(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def get_expense_payment_total(*, expense):
    return _money(
        expense.payments.aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )


def _record_status_change(*, expense, previous_status, changed_by, reason=""):
    if previous_status == expense.status:
        return None
    return ExpenseStatusChange.objects.create(
        expense=expense,
        previous_status=previous_status,
        new_status=expense.status,
        reason=reason.strip(),
        changed_by=changed_by,
    )


@transaction.atomic
def open_expense(*, expense, opened_by):
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status != Expense.Status.DRAFT:
        raise ValidationError("Può essere aperta solo una spesa in bozza.")
    expense.full_clean()
    previous_status = expense.status
    expense.status = Expense.Status.OPEN
    expense.save(update_fields=("status", "updated_at"))
    _record_status_change(
        expense=expense,
        previous_status=previous_status,
        changed_by=opened_by,
        reason="Spesa confermata",
    )
    return expense


@transaction.atomic
def add_expense_payment(
    *, expense, amount, payment_method, recorded_by, paid_at=None,
    reference="", notes=""
):
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status not in {
        Expense.Status.OPEN,
        Expense.Status.PARTIALLY_PAID,
    }:
        raise ValidationError("La spesa non è disponibile per il pagamento.")
    if payment_method not in {choice.value for choice in ExpensePayment.Method}:
        raise ValidationError("Il metodo di pagamento non è valido.")
    amount = _money(amount)
    if amount <= 0:
        raise ValidationError("L'importo del pagamento deve essere positivo.")
    ledger_total = get_expense_payment_total(expense=expense)
    if ledger_total != expense.paid_amount:
        raise ValidationError("Il totale pagato non coincide con il registro pagamenti.")
    if ledger_total + amount > expense.total_amount:
        raise ValidationError("Il pagamento supera il residuo della spesa.")

    payment = ExpensePayment.objects.create(
        expense=expense,
        amount=amount,
        payment_method=payment_method,
        paid_at=paid_at or timezone.now(),
        reference=reference.strip(),
        notes=notes.strip(),
        recorded_by=recorded_by,
    )
    previous_status = expense.status
    expense.paid_amount = ledger_total + amount
    expense.status = (
        Expense.Status.PAID
        if expense.paid_amount == expense.total_amount
        else Expense.Status.PARTIALLY_PAID
    )
    expense.save(update_fields=("paid_amount", "status", "updated_at"))
    _record_status_change(
        expense=expense,
        previous_status=previous_status,
        changed_by=recorded_by,
        reason="Pagamento registrato",
    )
    return payment


@transaction.atomic
def cancel_expense(*, expense, cancelled_by, reason, cancelled_at=None):
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status == Expense.Status.CANCELLED:
        raise ValidationError("La spesa è già annullata.")
    if expense.paid_amount > 0 or expense.payments.exists():
        raise ValidationError("Una spesa con pagamenti non può essere annullata.")
    if not reason.strip():
        raise ValidationError("L'annullamento richiede una motivazione.")
    previous_status = expense.status
    expense.status = Expense.Status.CANCELLED
    expense.cancelled_at = cancelled_at or timezone.now()
    expense.cancelled_by = cancelled_by
    expense.cancellation_reason = reason.strip()
    expense.save(update_fields=(
        "status", "cancelled_at", "cancelled_by",
        "cancellation_reason", "updated_at",
    ))
    _record_status_change(
        expense=expense,
        previous_status=previous_status,
        changed_by=cancelled_by,
        reason=reason,
    )
    return expense
