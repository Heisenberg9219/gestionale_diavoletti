import calendar
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import ShopSettings
from sales.models import Sale, SalePayment
from sales.services import add_sale_payment

from .models import (
    ExpiredVoucherAuthorization,
    Voucher,
    VoucherExpiryChange,
    VoucherMovement,
)


MONEY_QUANTIZER = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(
        MONEY_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def _add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _default_expiry(issued_at, voucher_type):
    settings_row = ShopSettings.objects.first()
    if settings_row is None:
        months = 6
    elif voucher_type == Voucher.Type.RETURN_CREDIT:
        months = settings_row.return_credit_months
    else:
        months = settings_row.voucher_validity_months
    return _add_months(issued_at, months)


def _new_code(voucher_type):
    prefixes = {
        Voucher.Type.GIFT_CARD: "GR",
        Voucher.Type.GIFT_LIST: "GL",
        Voucher.Type.RETURN_CREDIT: "BR",
    }
    return f"{prefixes[voucher_type]}-{uuid.uuid4().hex[:12].upper()}"


@transaction.atomic
def issue_voucher(
    *,
    voucher_type,
    initial_amount,
    issued_by,
    code=None,
    issued_at=None,
    expires_at=None,
    holder_first_name="",
    holder_last_name="",
    source_type="",
    source_id=None,
    notes="",
):
    if voucher_type not in {choice.value for choice in Voucher.Type}:
        raise ValidationError("Il tipo di buono non è valido.")

    initial_amount = _money(initial_amount)
    if initial_amount <= 0:
        raise ValidationError("Il valore iniziale deve essere positivo.")

    issued_at = issued_at or timezone.now()
    expires_at = expires_at or _default_expiry(issued_at, voucher_type)
    if expires_at <= issued_at:
        raise ValidationError("La scadenza deve essere successiva all'emissione.")

    voucher = Voucher(
        code=(code or _new_code(voucher_type)).strip().upper(),
        voucher_type=voucher_type,
        initial_amount=initial_amount,
        current_balance=initial_amount,
        issued_at=issued_at,
        expires_at=expires_at,
        holder_first_name=holder_first_name.strip(),
        holder_last_name=holder_last_name.strip(),
        source_type=source_type.strip(),
        source_id=source_id,
        issued_by=issued_by,
        notes=notes,
    )
    voucher.full_clean()
    voucher.save()

    VoucherMovement.objects.create(
        voucher=voucher,
        movement_type=VoucherMovement.Type.ISSUE,
        amount_delta=initial_amount,
        balance_after=initial_amount,
        occurred_at=issued_at,
        source_type=source_type.strip(),
        source_id=source_id,
        notes="Emissione del buono",
        created_by=issued_by,
    )
    return voucher


def get_voucher_ledger_balance(*, voucher):
    return _money(
        voucher.movements.aggregate(total=Sum("amount_delta"))["total"]
        or Decimal("0.00")
    )


@transaction.atomic
def change_voucher_expiry(*, voucher, new_expires_at, reason, changed_by):
    voucher = Voucher.objects.select_for_update().get(pk=voucher.pk)
    if voucher.status == Voucher.Status.CANCELLED:
        raise ValidationError("Un buono annullato non può essere modificato.")
    if not reason.strip():
        raise ValidationError("La modifica della scadenza richiede un motivo.")
    if new_expires_at <= voucher.issued_at:
        raise ValidationError("La nuova scadenza deve seguire l'emissione.")
    if new_expires_at == voucher.expires_at:
        raise ValidationError("La nuova scadenza coincide con quella attuale.")

    change = VoucherExpiryChange.objects.create(
        voucher=voucher,
        previous_expires_at=voucher.expires_at,
        new_expires_at=new_expires_at,
        reason=reason.strip(),
        changed_by=changed_by,
    )
    voucher.expires_at = new_expires_at
    voucher.save(update_fields=("expires_at", "updated_at"))
    return change


@transaction.atomic
def authorize_expired_voucher(
    *,
    voucher,
    sale,
    reason,
    authorized_by,
    authorized_at=None,
):
    voucher = Voucher.objects.select_for_update().get(pk=voucher.pk)
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    authorized_at = authorized_at or timezone.now()

    if sale.status != Sale.Status.OPEN:
        raise ValidationError("La vendita non è aperta.")
    if voucher.status != Voucher.Status.ACTIVE:
        raise ValidationError("Il buono non è utilizzabile.")
    if voucher.expires_at > authorized_at:
        raise ValidationError("Il buono non è scaduto.")
    if not reason.strip():
        raise ValidationError("L'autorizzazione richiede un motivo.")

    authorization, _ = ExpiredVoucherAuthorization.objects.get_or_create(
        voucher=voucher,
        sale=sale,
        defaults={
            "expires_at_snapshot": voucher.expires_at,
            "reason": reason.strip(),
            "authorized_at": authorized_at,
            "authorized_by": authorized_by,
        },
    )
    return authorization


@transaction.atomic
def redeem_voucher(
    *,
    voucher,
    sale,
    requested_amount,
    created_by,
    expired_authorization=None,
    occurred_at=None,
):
    voucher = Voucher.objects.select_for_update().get(pk=voucher.pk)
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    occurred_at = occurred_at or timezone.now()

    if sale.status != Sale.Status.OPEN:
        raise ValidationError("Il buono può essere usato solo su una vendita aperta.")
    if voucher.status != Voucher.Status.ACTIVE:
        raise ValidationError("Il buono non è utilizzabile.")
    if get_voucher_ledger_balance(voucher=voucher) != voucher.current_balance:
        raise ValidationError("Il saldo del buono non coincide con il registro movimenti.")

    if voucher.expires_at <= occurred_at:
        authorization = expired_authorization
        if authorization is None:
            authorization = ExpiredVoucherAuthorization.objects.filter(
                voucher=voucher,
                sale=sale,
            ).first()
        if (
            authorization is None
            or authorization.voucher_id != voucher.id
            or authorization.sale_id != sale.id
        ):
            raise ValidationError("Il buono scaduto richiede un'autorizzazione.")

    requested_amount = _money(requested_amount)
    if requested_amount <= 0:
        raise ValidationError("L'importo richiesto deve essere positivo.")

    paid_amount = _money(
        sale.payments.aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    remaining_sale_amount = _money(sale.final_total_amount - paid_amount)
    if remaining_sale_amount <= 0:
        raise ValidationError("La vendita risulta già interamente pagata.")

    applied_amount = min(
        requested_amount,
        voucher.current_balance,
        remaining_sale_amount,
    )
    new_balance = _money(voucher.current_balance - applied_amount)

    movement = VoucherMovement.objects.create(
        voucher=voucher,
        movement_type=VoucherMovement.Type.REDEMPTION,
        amount_delta=-applied_amount,
        balance_after=new_balance,
        occurred_at=occurred_at,
        source_type="sales.Sale",
        source_id=sale.id,
        notes=f"Utilizzo sulla vendita {sale.id}",
        created_by=created_by,
    )

    voucher.current_balance = new_balance
    if new_balance == 0:
        voucher.status = Voucher.Status.EXHAUSTED
    voucher.save(update_fields=("current_balance", "status", "updated_at"))

    payment_method = (
        SalePayment.Method.STORE_CREDIT
        if voucher.voucher_type == Voucher.Type.RETURN_CREDIT
        else SalePayment.Method.GIFT_CARD
    )
    payment = add_sale_payment(
        sale=sale,
        method=payment_method,
        amount=applied_amount,
        transaction_reference=voucher.code,
        source_type="vouchers.Voucher",
        source_id=voucher.id,
        occurred_at=occurred_at,
        created_by=created_by,
    )
    return movement, payment


@transaction.atomic
def cancel_voucher(*, voucher, cancelled_by, reason, cancelled_at=None):
    voucher = Voucher.objects.select_for_update().get(pk=voucher.pk)
    if voucher.status != Voucher.Status.ACTIVE:
        raise ValidationError("Può essere annullato solo un buono attivo.")
    if not reason.strip():
        raise ValidationError("L'annullamento richiede un motivo.")

    cancelled_at = cancelled_at or timezone.now()
    previous_balance = voucher.current_balance
    if previous_balance <= 0:
        raise ValidationError("Il buono non ha un saldo da annullare.")
    VoucherMovement.objects.create(
        voucher=voucher,
        movement_type=VoucherMovement.Type.CANCELLATION,
        amount_delta=-previous_balance,
        balance_after=Decimal("0.00"),
        occurred_at=cancelled_at,
        notes=reason.strip(),
        created_by=cancelled_by,
    )
    voucher.current_balance = Decimal("0.00")
    voucher.status = Voucher.Status.CANCELLED
    voucher.cancelled_at = cancelled_at
    voucher.cancelled_by = cancelled_by
    voucher.cancellation_reason = reason.strip()
    voucher.save(
        update_fields=(
            "current_balance",
            "status",
            "cancelled_at",
            "cancelled_by",
            "cancellation_reason",
            "updated_at",
        )
    )
    return voucher
