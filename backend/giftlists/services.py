from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from inventory.models import StockBalance
from vouchers.models import Voucher
from vouchers.services import issue_voucher

from .models import (
    GiftList,
    GiftListContribution,
    GiftListItem,
    GiftListItemPurchase,
    ReservedStockSaleAuthorization,
)


def _money(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def get_reserved_stock_warning(*, sale, variant, quantity):
    stock_quantity = (
        StockBalance.objects.filter(
            variant=variant,
            location=sale.location,
        ).values_list("quantity_on_hand", flat=True).first()
        or 0
    )
    items = list(
        GiftListItem.objects.filter(
            gift_list__status=GiftList.Status.OPEN,
            gift_list__location=sale.location,
            variant=variant,
            reserved_quantity__gt=F("purchased_quantity"),
        ).select_related("gift_list")
    )
    reserved_quantity = sum(
        item.remaining_reserved_quantity for item in items
    )
    unreserved_quantity = max(stock_quantity - reserved_quantity, 0)
    affected = quantity > unreserved_quantity and reserved_quantity > 0
    return {
        "requires_authorization": affected,
        "stock_quantity": stock_quantity,
        "reserved_quantity": reserved_quantity,
        "unreserved_quantity": unreserved_quantity,
        "requested_sale_quantity": quantity,
        "affected_list_codes": sorted(
            {item.gift_list.code for item in items}
        ),
    }


@transaction.atomic
def authorize_reserved_stock_sale(
    *, sale, variant, quantity, reason, authorized_by
):
    if sale.status != sale.Status.OPEN:
        raise ValidationError("La vendita non è aperta.")
    if not reason.strip():
        raise ValidationError("La conferma richiede una motivazione.")
    warning = get_reserved_stock_warning(
        sale=sale,
        variant=variant,
        quantity=quantity,
    )
    if not warning["requires_authorization"]:
        raise ValidationError("Questa vendita non intacca articoli accantonati.")
    return ReservedStockSaleAuthorization.objects.create(
        sale=sale,
        variant=variant,
        requested_sale_quantity=quantity,
        stock_quantity_snapshot=warning["stock_quantity"],
        reserved_quantity_snapshot=warning["reserved_quantity"],
        affected_list_codes=warning["affected_list_codes"],
        reason=reason.strip(),
        authorized_by=authorized_by,
    )


def validate_reserved_stock_sale(
    *, sale, variant, quantity, authorization=None, gift_list_item=None
):
    if gift_list_item is not None:
        gift_list_item = GiftListItem.objects.select_related(
            "gift_list"
        ).get(pk=gift_list_item.pk)
        if (
            gift_list_item.gift_list.status != GiftList.Status.OPEN
            or gift_list_item.variant_id != variant.id
        ):
            raise ValidationError("La voce selezionata non è valida per questa vendita.")
        if quantity <= gift_list_item.remaining_reserved_quantity:
            return {
                "requires_authorization": False,
                "gift_list_code": gift_list_item.gift_list.code,
            }
    warning = get_reserved_stock_warning(
        sale=sale,
        variant=variant,
        quantity=quantity,
    )
    if not warning["requires_authorization"]:
        return warning
    if authorization is None:
        raise ValidationError(
            "L'articolo è accantonato in una lista regalo. "
            "Confermare esplicitamente per proseguire con la vendita."
        )
    valid = (
        authorization.sale_id == sale.id
        and authorization.variant_id == variant.id
        and authorization.requested_sale_quantity == quantity
    )
    if not valid:
        raise ValidationError("La conferma dell'articolo accantonato non è valida.")
    return warning


@transaction.atomic
def set_gift_list_item(
    *, gift_list, variant, requested_quantity, reserved_quantity, added_by,
    notes=""
):
    gift_list = GiftList.objects.select_for_update().get(pk=gift_list.pk)
    if gift_list.status != GiftList.Status.OPEN:
        raise ValidationError("La lista non è aperta.")
    if gift_list.mode != GiftList.Mode.PRODUCTS:
        raise ValidationError("La lista non è configurata per gli articoli.")
    if requested_quantity <= 0:
        raise ValidationError("La quantità richiesta deve essere positiva.")
    if reserved_quantity < 0 or reserved_quantity > requested_quantity:
        raise ValidationError("La quantità accantonata non è valida.")
    existing_item = GiftListItem.objects.filter(
        gift_list=gift_list,
        variant=variant,
    ).first()
    if (
        existing_item is not None
        and existing_item.purchased_quantity > requested_quantity
    ):
        raise ValidationError("Sono già stati acquistati più articoli del nuovo limite.")
    item, _ = GiftListItem.objects.update_or_create(
        gift_list=gift_list,
        variant=variant,
        defaults={
            "requested_quantity": requested_quantity,
            "reserved_quantity": reserved_quantity,
            "added_by": added_by,
            "notes": notes.strip(),
        },
    )
    return item


@transaction.atomic
def add_contribution(
    *, gift_list, first_name, last_name, amount, payment_method,
    recorded_by, occurred_at=None, notes=""
):
    gift_list = GiftList.objects.select_for_update().get(pk=gift_list.pk)
    if gift_list.status != GiftList.Status.OPEN:
        raise ValidationError("La lista non è aperta.")
    if gift_list.mode != GiftList.Mode.CONTRIBUTIONS:
        raise ValidationError("La lista non è configurata per i contributi.")
    amount = _money(amount)
    if amount <= 0:
        raise ValidationError("Il contributo deve essere positivo.")
    if payment_method not in {
        choice.value for choice in GiftListContribution.PaymentMethod
    }:
        raise ValidationError("Il metodo di pagamento non è valido.")
    return GiftListContribution.objects.create(
        gift_list=gift_list,
        contributor_first_name=first_name.strip(),
        contributor_last_name=last_name.strip(),
        amount=amount,
        payment_method=payment_method,
        occurred_at=occurred_at or timezone.now(),
        recorded_by=recorded_by,
        notes=notes.strip(),
    )


@transaction.atomic
def record_item_purchase(*, item, sale_line, quantity, recorded_by):
    item = GiftListItem.objects.select_for_update().select_related(
        "gift_list"
    ).get(pk=item.pk)
    if item.gift_list.status != GiftList.Status.OPEN:
        raise ValidationError("La lista non è aperta.")
    if sale_line.variant_id != item.variant_id:
        raise ValidationError("La riga vendita non corrisponde all'articolo.")
    if quantity <= 0 or quantity > sale_line.quantity:
        raise ValidationError("La quantità acquistata non è valida.")
    if item.purchased_quantity + quantity > item.requested_quantity:
        raise ValidationError("La quantità supera quella richiesta nella lista.")
    purchase = GiftListItemPurchase.objects.create(
        item=item,
        sale_line=sale_line,
        quantity=quantity,
        recorded_by=recorded_by,
    )
    item.purchased_quantity = F("purchased_quantity") + quantity
    item.save(update_fields=("purchased_quantity", "updated_at"))
    item.refresh_from_db()
    return purchase


@transaction.atomic
def close_gift_list(*, gift_list, closed_by, closed_at=None):
    gift_list = GiftList.objects.select_for_update().get(pk=gift_list.pk)
    if gift_list.status != GiftList.Status.OPEN:
        raise ValidationError("Può essere chiusa solo una lista aperta.")
    closed_at = closed_at or timezone.now()
    voucher = None
    if gift_list.mode == GiftList.Mode.CONTRIBUTIONS:
        total = _money(
            gift_list.contributions.aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        if total <= 0:
            raise ValidationError("La lista non contiene contributi da convertire.")
        voucher = issue_voucher(
            voucher_type=Voucher.Type.GIFT_LIST,
            initial_amount=total,
            issued_by=closed_by,
            issued_at=closed_at,
            holder_first_name=gift_list.beneficiary_first_name,
            holder_last_name=gift_list.beneficiary_last_name,
            source_type="giftlists.GiftList",
            source_id=gift_list.id,
            notes=f"Buono generato dalla lista {gift_list.code}",
        )
    gift_list.status = GiftList.Status.CLOSED
    gift_list.closed_at = closed_at
    gift_list.closed_by = closed_by
    gift_list.generated_voucher = voucher
    gift_list.save(update_fields=(
        "status", "closed_at", "closed_by", "generated_voucher", "updated_at"
    ))
    return gift_list, voucher
