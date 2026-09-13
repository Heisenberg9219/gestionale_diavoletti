from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Sale, SaleDraftChange, SaleLine, SalePayment
from .services import _refresh_sale_totals, set_sale_total_override


def _open_sale(sale, reason):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 255:
        raise ValidationError("Specificare una motivazione entro 255 caratteri.")
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status != Sale.Status.OPEN:
        raise ValidationError("Operazione consentita solo su vendite aperte.")
    return sale


@transaction.atomic
def remove_draft_payment(*, sale, payment, removed_by, reason):
    from vouchers.models import Voucher, VoucherMovement
    sale = _open_sale(sale, reason)
    payment = SalePayment.objects.select_for_update().filter(pk=payment.pk).first()
    if payment is None:
        raise ValidationError("Pagamento gia' rimosso.")
    if payment.sale_id != sale.pk:
        raise ValidationError("Il pagamento non appartiene alla vendita.")
    snapshot = {"payment_id": str(payment.pk), "method": payment.method, "amount": str(payment.amount), "transaction_reference": payment.transaction_reference, "source_type": payment.source_type, "source_id": str(payment.source_id) if payment.source_id else None}
    if payment.source_type == "vouchers.Voucher":
        voucher = Voucher.objects.select_for_update().get(pk=payment.source_id)
        if voucher.status not in (Voucher.Status.ACTIVE, Voucher.Status.EXHAUSTED):
            raise ValidationError("Il buono non consente il ripristino automatico.")
        voucher.current_balance += payment.amount
        voucher.status = Voucher.Status.ACTIVE
        voucher.save(update_fields=("current_balance", "status", "updated_at"))
        movement = VoucherMovement.objects.create(voucher=voucher, movement_type=VoucherMovement.Type.ADJUSTMENT, amount_delta=payment.amount, balance_after=voucher.current_balance, source_type="sales.SalePayment", source_id=payment.pk, notes=reason.strip(), created_by=removed_by)
        snapshot["voucher_movement_id"] = str(movement.pk)
    elif payment.source_type or payment.source_id or payment.method in (SalePayment.Method.GIFT_CARD, SalePayment.Method.STORE_CREDIT):
        raise ValidationError("Questo pagamento richiede una riconciliazione dedicata.")
    change = SaleDraftChange.objects.create(sale=sale, operation="REMOVE_PAYMENT", reason=reason.strip(), snapshot=snapshot, created_by=removed_by)
    payment.delete()
    return change


@transaction.atomic
def remove_draft_line(*, sale, line, removed_by, reason):
    sale = _open_sale(sale, reason)
    line = SaleLine.objects.select_for_update().filter(pk=line.pk).first()
    if line is None:
        raise ValidationError("Riga gia' rimossa.")
    if line.sale_id != sale.pk:
        raise ValidationError("La riga non appartiene alla vendita.")
    if sale.payments.exists():
        raise ValidationError("Rimuovere prima i pagamenti.")
    if sale.loyalty_reward_redemptions.filter(status="APPLIED").exists():
        raise ValidationError("Rimuovere prima il premio fedelta' applicato.")
    if line.promotion_allocations.exists():
        raise ValidationError("La riga ha uno storico promozioni: annullare la vendita e crearne una nuova.")
    if sale.manual_total_override_amount is not None:
        set_sale_total_override(sale=sale, final_total_amount=sale.calculated_total_amount, manual_override_reason=reason, manual_override_by=removed_by)
        sale.refresh_from_db()
    change = SaleDraftChange.objects.create(sale=sale, operation="REMOVE_LINE", reason=reason.strip(), snapshot={"line_id": str(line.pk), "variant": str(line.variant_id), "quantity": line.quantity, "net_amount": str(line.net_amount)}, created_by=removed_by)
    line.delete()
    _refresh_sale_totals(sale)
    return change


@transaction.atomic
def cancel_draft_sale(*, sale, cancelled_by, reason):
    sale = _open_sale(sale, reason)
    if sale.payments.exists():
        raise ValidationError("Rimuovere e riconciliare prima i pagamenti.")
    from loyalty.services import cancel_reward_redemption
    for redemption in sale.loyalty_reward_redemptions.filter(status="APPLIED"):
        cancel_reward_redemption(redemption=redemption, cancelled_by=cancelled_by, reason=reason)
    SaleDraftChange.objects.create(sale=sale, operation="CANCEL", reason=reason.strip(), snapshot={"total": str(sale.final_total_amount)}, created_by=cancelled_by)
    sale.status = Sale.Status.CANCELLED
    sale.cancelled_by = cancelled_by
    sale.cancelled_at = timezone.now()
    sale.save(update_fields=("status", "cancelled_by", "cancelled_at", "updated_at"))
    return sale
