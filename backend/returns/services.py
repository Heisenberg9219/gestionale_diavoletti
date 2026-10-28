from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from inventory.models import StockMovement
from inventory.services import post_stock_movement
from loyalty.models import LoyaltyPointMovement
from loyalty.services import record_point_movement
from sales.models import Sale, SaleLine
from vouchers.models import Voucher
from vouchers.services import cancel_voucher, issue_voucher

from .models import (
    CustomerReturn,
    CustomerReturnLine,
    CustomerReturnNumberSequence,
)


def _money(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _next_return_number(*, occurred_at):
    sequence, _ = CustomerReturnNumberSequence.objects.get_or_create(
        year=occurred_at.year,
        defaults={"last_number": 0},
    )
    sequence = CustomerReturnNumberSequence.objects.select_for_update().get(
        pk=sequence.pk
    )
    sequence.last_number += 1
    sequence.save(update_fields=("last_number", "updated_at"))
    return f"RES-{occurred_at.year}-{sequence.last_number:06d}"


@transaction.atomic
def create_customer_return(*, original_sale, reason, created_by, notes=""):
    original_sale = Sale.objects.select_for_update().get(pk=original_sale.pk)
    if original_sale.status != Sale.Status.CONFIRMED:
        raise ValidationError("Il reso richiede una vendita confermata.")
    if not reason.strip():
        raise ValidationError("Il motivo del reso è obbligatorio.")
    return CustomerReturn.objects.create(
        original_sale=original_sale,
        customer=original_sale.customer,
        location=original_sale.location,
        reason=reason.strip(),
        notes=notes.strip(),
        created_by=created_by,
    )


@transaction.atomic
def set_return_line(
    *, customer_return, original_sale_line, quantity, restock=True
):
    customer_return = CustomerReturn.objects.select_for_update().get(
        pk=customer_return.pk
    )
    if customer_return.status != CustomerReturn.Status.DRAFT:
        raise ValidationError("Le righe possono essere modificate solo in bozza.")
    original_sale_line = SaleLine.objects.select_for_update().get(
        pk=original_sale_line.pk
    )
    if original_sale_line.sale_id != customer_return.original_sale_id:
        raise ValidationError("La riga non appartiene alla vendita originale.")
    if quantity <= 0:
        raise ValidationError("La quantità restituita deve essere positiva.")

    previous_returns = CustomerReturnLine.objects.filter(
        original_sale_line=original_sale_line,
        customer_return__status=CustomerReturn.Status.CONFIRMED,
    ).aggregate(quantity=Sum("quantity"), amount=Sum("total_refund_amount"))
    returned_quantity = previous_returns["quantity"] or 0
    returned_amount = previous_returns["amount"] or Decimal("0.00")
    remaining_quantity = original_sale_line.quantity - returned_quantity
    if quantity > remaining_quantity:
        raise ValidationError("La quantità supera quella ancora restituibile.")

    remaining_amount = _money(original_sale_line.net_amount - returned_amount)
    unit_amount = _money(
        original_sale_line.net_amount / Decimal(original_sale_line.quantity)
    )
    total_amount = (
        remaining_amount
        if quantity == remaining_quantity
        else _money(unit_amount * Decimal(quantity))
    )
    line, _ = CustomerReturnLine.objects.update_or_create(
        customer_return=customer_return,
        original_sale_line=original_sale_line,
        defaults={
            "quantity": quantity,
            "restock": restock,
            "unit_refund_amount": unit_amount,
            "total_refund_amount": total_amount,
            "sku_snapshot": original_sale_line.sku_snapshot,
            "product_name_snapshot": original_sale_line.product_name_snapshot,
        },
    )
    return line


def get_returnable_quantity(*, original_sale_line):
    returned = CustomerReturnLine.objects.filter(
        original_sale_line=original_sale_line,
        customer_return__status=CustomerReturn.Status.CONFIRMED,
    ).aggregate(total=Sum("quantity"))["total"] or 0
    return original_sale_line.quantity - returned


def _calculate_points_reversal(*, customer_return, refund_total):
    sale = customer_return.original_sale
    if sale.customer_id is None or sale.final_total_amount <= 0:
        return 0
    earned_points = LoyaltyPointMovement.objects.filter(
        customer=sale.customer,
        movement_type=LoyaltyPointMovement.Type.EARNED,
        source_type="sales.Sale",
        source_id=sale.id,
    ).aggregate(total=Sum("points_delta"))["total"] or 0
    if earned_points <= 0:
        return 0
    prior_returns = CustomerReturn.objects.filter(
        original_sale=sale,
        status=CustomerReturn.Status.CONFIRMED,
    ).aggregate(
        amount=Sum("total_refund_amount"),
        points=Sum("points_reversed"),
    )
    prior_amount = prior_returns["amount"] or Decimal("0.00")
    prior_points = prior_returns["points"] or 0
    cumulative_amount = min(
        prior_amount + refund_total,
        sale.final_total_amount,
    )
    target_points = int(
        Decimal(earned_points)
        * cumulative_amount
        / sale.final_total_amount
    )
    return max(target_points - prior_points, 0)


@transaction.atomic
def confirm_customer_return(
    *, customer_return, confirmed_by, confirmed_at=None
):
    customer_return = (
        CustomerReturn.objects.select_for_update(of=("self",))
        .select_related("original_sale", "customer", "location")
        .get(pk=customer_return.pk)
    )
    if customer_return.status != CustomerReturn.Status.DRAFT:
        raise ValidationError("Può essere confermato solo un reso in bozza.")
    sale = Sale.objects.select_for_update().get(
        pk=customer_return.original_sale_id
    )
    if sale.status != Sale.Status.CONFIRMED:
        raise ValidationError("La vendita originale non è confermata.")
    lines = list(
        customer_return.lines.select_for_update().select_related(
            "original_sale_line", "original_sale_line__variant"
        )
    )
    if not lines:
        raise ValidationError("Il reso non contiene articoli.")

    for line in lines:
        if line.quantity > get_returnable_quantity(
            original_sale_line=line.original_sale_line
        ):
            raise ValidationError("Una quantità non è più restituibile.")
    refund_total = _money(sum(
        (line.total_refund_amount for line in lines),
        Decimal("0.00"),
    ))
    if refund_total <= 0:
        raise ValidationError("L'importo del reso deve essere positivo.")

    confirmed_at = confirmed_at or timezone.now()
    return_number = _next_return_number(occurred_at=confirmed_at)
    holder_first_name = (
        customer_return.customer.first_name if customer_return.customer else ""
    )
    holder_last_name = (
        customer_return.customer.last_name if customer_return.customer else ""
    )
    voucher = issue_voucher(
        voucher_type=Voucher.Type.RETURN_CREDIT,
        initial_amount=refund_total,
        issued_by=confirmed_by,
        issued_at=confirmed_at,
        holder_first_name=holder_first_name,
        holder_last_name=holder_last_name,
        source_type="returns.CustomerReturn",
        source_id=customer_return.id,
        notes=f"Buono generato dal reso {return_number}",
    )

    for line in lines:
        if line.restock:
            post_stock_movement(
                variant=line.original_sale_line.variant,
                location=customer_return.location,
                movement_type=StockMovement.Type.CUSTOMER_RETURN,
                quantity_delta=line.quantity,
                unit_cost=line.original_sale_line.unit_cost_snapshot,
                occurred_at=confirmed_at,
                source_type="returns.CustomerReturn",
                source_id=customer_return.id,
                reference_number=return_number,
                created_by=confirmed_by,
            )

    points_reversed = _calculate_points_reversal(
        customer_return=customer_return,
        refund_total=refund_total,
    )
    if points_reversed > 0:
        record_point_movement(
            customer=customer_return.customer,
            points_delta=-points_reversed,
            movement_type=LoyaltyPointMovement.Type.RETURN_REVERSAL,
            source_type="returns.CustomerReturn",
            source_id=customer_return.id,
            occurred_at=confirmed_at,
            notes=f"Storno punti per il reso {return_number}",
            created_by=confirmed_by,
        )

    customer_return.number = return_number
    customer_return.status = CustomerReturn.Status.CONFIRMED
    customer_return.total_refund_amount = refund_total
    customer_return.points_reversed = points_reversed
    customer_return.return_voucher = voucher
    customer_return.confirmed_at = confirmed_at
    customer_return.confirmed_by = confirmed_by
    customer_return.save(update_fields=(
        "number", "status", "total_refund_amount", "points_reversed",
        "return_voucher", "confirmed_at", "confirmed_by", "updated_at",
    ))
    return customer_return


@transaction.atomic
def cancel_draft_return(*, customer_return, cancelled_by, reason):
    customer_return = CustomerReturn.objects.select_for_update().get(
        pk=customer_return.pk
    )
    if customer_return.status != CustomerReturn.Status.DRAFT:
        raise ValidationError("Può essere annullato solo un reso in bozza.")
    if not reason.strip():
        raise ValidationError("L'annullamento richiede una motivazione.")
    customer_return.status = CustomerReturn.Status.CANCELLED
    customer_return.cancelled_at = timezone.now()
    customer_return.cancelled_by = cancelled_by
    customer_return.cancellation_reason = reason.strip()
    customer_return.save(update_fields=(
        "status", "cancelled_at", "cancelled_by",
        "cancellation_reason", "updated_at",
    ))
    return customer_return


@transaction.atomic
def cancel_confirmed_return(*, customer_return, cancelled_by, reason, cancelled_at=None):
    """Annulla un reso già confermato disfacendo ciò che la conferma aveva fatto.

    È consentito solo finché il buono generato non è stato usato: il capo torna
    a risultare venduto (esce di nuovo dal magazzino), il buono viene annullato
    e al cliente vengono restituiti i punti stornati. Il reso resta nello
    storico con stato "Annullato".
    """
    customer_return = (
        CustomerReturn.objects.select_for_update(of=("self",))
        .select_related("return_voucher", "customer", "location")
        .get(pk=customer_return.pk)
    )
    if customer_return.status != CustomerReturn.Status.CONFIRMED:
        raise ValidationError("Può essere annullato solo un reso confermato.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("L'annullamento richiede una motivazione.")

    voucher = Voucher.objects.select_for_update().get(
        pk=customer_return.return_voucher_id
    )
    if voucher.status != Voucher.Status.ACTIVE:
        raise ValidationError(
            "Il buono del reso non è più attivo: il reso non può essere annullato."
        )
    if voucher.current_balance != voucher.initial_amount:
        raise ValidationError(
            "Il buono del reso è già stato usato, anche in parte: "
            "il reso non può essere annullato."
        )

    cancelled_at = cancelled_at or timezone.now()
    note = f"Annullamento reso {customer_return.number}: {reason}"

    for line in customer_return.lines.select_related(
        "original_sale_line", "original_sale_line__variant"
    ):
        if not line.restock:
            continue
        try:
            post_stock_movement(
                variant=line.original_sale_line.variant,
                location=customer_return.location,
                movement_type=StockMovement.Type.ADJUSTMENT_OUT,
                quantity_delta=-line.quantity,
                occurred_at=cancelled_at,
                source_type="returns.CustomerReturn",
                source_id=customer_return.id,
                reference_number=customer_return.number,
                notes=note,
                created_by=cancelled_by,
            )
        except ValidationError as exc:
            raise ValidationError(
                f"{line.product_name_snapshot} ({line.sku_snapshot}) non è più "
                "in giacenza, probabilmente è stato rivenduto: "
                "il reso non può essere annullato."
            ) from exc

    cancel_voucher(
        voucher=voucher,
        cancelled_by=cancelled_by,
        reason=note[:255],
        cancelled_at=cancelled_at,
    )

    if customer_return.points_reversed > 0 and customer_return.customer_id:
        record_point_movement(
            customer=customer_return.customer,
            points_delta=customer_return.points_reversed,
            movement_type=LoyaltyPointMovement.Type.MANUAL_ADJUSTMENT,
            source_type="returns.CustomerReturn",
            source_id=customer_return.id,
            occurred_at=cancelled_at,
            notes=f"Ripristino punti per {note}",
            created_by=cancelled_by,
        )

    customer_return.status = CustomerReturn.Status.CANCELLED
    customer_return.cancelled_at = cancelled_at
    customer_return.cancelled_by = cancelled_by
    customer_return.cancellation_reason = reason[:255]
    customer_return.save(update_fields=(
        "status", "cancelled_at", "cancelled_by",
        "cancellation_reason", "updated_at",
    ))
    return customer_return
