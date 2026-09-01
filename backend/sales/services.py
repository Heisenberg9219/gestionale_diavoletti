from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from inventory.models import (
    StockBalance,
    StockMovement,
    VariantInventoryCost,
)
from inventory.services import post_stock_movement
from pricing.models import VariantSalePrice
from .models import (
    CashRegister,
    CashSession,
    Sale,
    SaleLine,
    SaleNumberSequence,
    SalePayment,
)


@transaction.atomic
def open_cash_session(
    *,
    cash_register,
    opened_by,
    opening_cash_amount="0.00",
    opened_at=None,
    notes="",
):
    cash_register = CashRegister.objects.select_for_update().get(
        pk=cash_register.pk
    )

    if not cash_register.is_active:
        raise ValidationError("La postazione di cassa non è attiva.")

    if cash_register.sessions.filter(
        status=CashSession.Status.OPEN
    ).exists():
        raise ValidationError(
            "La postazione ha già una sessione aperta."
        )

    opening_cash_amount = Decimal(str(opening_cash_amount))
    if opening_cash_amount < 0:
        raise ValidationError(
            "Il fondo cassa iniziale non può essere negativo."
        )

    return CashSession.objects.create(
        cash_register=cash_register,
        opened_at=opened_at or timezone.now(),
        opened_by=opened_by,
        opening_cash_amount=opening_cash_amount,
        notes=notes,
    )


@transaction.atomic
def close_cash_session(
    *,
    cash_session,
    counted_cash_amount,
    closed_by,
    closed_at=None,
):
    cash_session = (
        CashSession.objects.select_for_update()
        .select_related("cash_register")
        .get(pk=cash_session.pk)
    )

    if cash_session.status != CashSession.Status.OPEN:
        raise ValidationError("La sessione di cassa non è aperta.")

    counted_cash_amount = Decimal(str(counted_cash_amount))
    if counted_cash_amount < 0:
        raise ValidationError(
            "Il contante contato non può essere negativo."
        )

    cash_sales = SalePayment.objects.filter(
        sale__cash_session=cash_session,
        sale__status=Sale.Status.CONFIRMED,
        method=SalePayment.Method.CASH,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    expected_cash_amount = (
        cash_session.opening_cash_amount + cash_sales
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    cash_difference = (
        counted_cash_amount - expected_cash_amount
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    cash_session.status = CashSession.Status.CLOSED
    cash_session.closed_at = closed_at or timezone.now()
    cash_session.closed_by = closed_by
    cash_session.expected_cash_amount = expected_cash_amount
    cash_session.counted_cash_amount = counted_cash_amount
    cash_session.cash_difference = cash_difference
    cash_session.save(
        update_fields=(
            "status",
            "closed_at",
            "closed_by",
            "expected_cash_amount",
            "counted_cash_amount",
            "cash_difference",
            "updated_at",
        )
    )

    return cash_session

MONEY_QUANTIZER = Decimal("0.01")

def _next_sale_number(*, occurred_at):
    year = occurred_at.year

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            [year],
        )

    sequence, _ = SaleNumberSequence.objects.get_or_create(
        year=year,
        defaults={"last_number": 0},
    )
    sequence = SaleNumberSequence.objects.select_for_update().get(
        pk=sequence.pk
    )
    sequence.last_number += 1
    sequence.save(
        update_fields=(
            "last_number",
            "updated_at",
        )
    )

    return f"V-{year}-{sequence.last_number:06d}"

def _money(value):
    return Decimal(value).quantize(
        MONEY_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def _included_tax(*, gross_amount, tax_percentage):
    tax_percentage = Decimal(tax_percentage)

    if gross_amount == 0 or tax_percentage == 0:
        return Decimal("0.00")

    return _money(
        gross_amount
        * tax_percentage
        / (Decimal("100.00") + tax_percentage)
    )


def _refresh_sale_totals(sale):
    lines = list(sale.lines.all())

    sale.subtotal_amount = _money(
        sum(
            (line.gross_amount for line in lines),
            Decimal("0.00"),
        )
    )
    sale.discount_amount = _money(
        sum(
            (line.discount_amount for line in lines),
            Decimal("0.00"),
        )
    )
    sale.tax_amount = _money(
        sum(
            (line.tax_amount for line in lines),
            Decimal("0.00"),
        )
    )
    sale.calculated_total_amount = _money(
        sum(
            (
                line.net_amount - line.total_override_share
                for line in lines
            ),
            Decimal("0.00"),
        )
    )
    sale.total_cost_amount = _money(
        sum(
            (line.total_cost_amount for line in lines),
            Decimal("0.00"),
        )
    )

    if sale.manual_total_override_amount is None:
        sale.manual_total_adjustment = Decimal("0.00")
        sale.final_total_amount = sale.calculated_total_amount
    else:
        sale.manual_total_adjustment = _money(
            sale.manual_total_override_amount
            - sale.calculated_total_amount
        )
        sale.final_total_amount = sale.manual_total_override_amount

    sale.save(
        update_fields=(
            "subtotal_amount",
            "discount_amount",
            "tax_amount",
            "calculated_total_amount",
            "manual_total_adjustment",
            "final_total_amount",
            "total_cost_amount",
            "updated_at",
        )
    )

@transaction.atomic
def set_sale_line(
    *,
    sale,
    variant,
    quantity,
    manual_unit_price=None,
    manual_override_reason="",
    manual_override_by=None,
):
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if sale.status != Sale.Status.OPEN:
        raise ValidationError(
            "Le righe possono essere modificate solo a vendita aperta."
        )

    if sale.payments.exists():
        raise ValidationError(
            "Rimuovere i pagamenti prima di modificare "
            "le righe della vendita."
        )

    if quantity <= 0:
        raise ValidationError(
            "La quantità deve essere maggiore di zero."
        )

    variant = (
        type(variant).objects.select_related(
            "product",
            "product__tax_rate",
            "color",
            "size",
        )
        .get(pk=variant.pk)
    )

    now = timezone.now()
    sale_price = (
        VariantSalePrice.objects.select_for_update(of=("self",))
        .filter(
            variant=variant,
            valid_from__lte=now,
        )
        .filter(
            Q(valid_until__isnull=True)
            | Q(valid_until__gt=now)
        )
        .order_by("-valid_from")
        .first()
    )

    if sale_price is None:
        raise ValidationError(
            "La variante non ha un prezzo di vendita attivo."
        )

    base_unit_price = sale_price.amount
    final_unit_price = base_unit_price

    if manual_unit_price is not None:
        manual_unit_price = _money(
            Decimal(str(manual_unit_price))
        )

        if manual_unit_price < 0:
            raise ValidationError(
                "Il prezzo manuale non può essere negativo."
            )

        if not manual_override_reason.strip():
            raise ValidationError(
                "La modifica manuale richiede una motivazione."
            )

        final_unit_price = manual_unit_price
    else:
        manual_override_reason = ""
        manual_override_by = None

    gross_amount = _money(
        base_unit_price * Decimal(quantity)
    )
    net_amount = _money(
        final_unit_price * Decimal(quantity)
    )
    discount_amount = max(
        gross_amount - net_amount,
        Decimal("0.00"),
    )
    manual_adjustment = _money(net_amount - gross_amount)

    tax_percentage = variant.product.tax_rate.percentage
    tax_amount = _included_tax(
        gross_amount=net_amount,
        tax_percentage=tax_percentage,
    )

    inventory_cost = VariantInventoryCost.objects.filter(
        variant=variant,
    ).first()
    unit_cost = (
        inventory_cost.weighted_average_unit_cost
        if inventory_cost is not None
        else Decimal("0.0000")
    )
    total_cost = _money(unit_cost * Decimal(quantity))

    line = sale.lines.select_for_update().filter(
        variant=variant,
    ).first()

    if (
        line is not None
        and line.promotion_allocations.filter(
            application__status="APPLIED",
        ).exists()
    ):
        raise ValidationError(
            "Rimuovere la promozione prima di modificare la riga."
        )

    if line is None:
        line = SaleLine(
            sale=sale,
            variant=variant,
        )

    line.quantity = quantity
    line.sku_snapshot = variant.sku
    line.product_name_snapshot = variant.product.name
    line.color_snapshot = (
        variant.color.name if variant.color is not None else ""
    )
    line.size_snapshot = variant.size.label
    line.pricing_mode = SaleLine.PricingMode.STANDARD
    line.source_sale_price = sale_price
    line.base_unit_price = base_unit_price
    line.manual_unit_price = manual_unit_price
    line.final_unit_price = final_unit_price
    line.gross_amount = gross_amount
    line.discount_amount = discount_amount
    line.net_amount = net_amount
    line.tax_percentage = tax_percentage
    line.tax_amount = tax_amount
    line.unit_cost_snapshot = unit_cost
    line.total_cost_amount = total_cost
    line.manual_adjustment = manual_adjustment
    line.total_override_share = Decimal("0.00")
    line.manual_override_reason = manual_override_reason
    line.manual_override_by = manual_override_by
    line.save()

    sale.manual_total_override_amount = None
    sale.manual_total_adjustment = Decimal("0.00")
    sale.manual_override_reason = ""
    sale.manual_override_by = None
    sale.save(
        update_fields=(
            "manual_total_override_amount",
            "manual_total_adjustment",
            "manual_override_reason",
            "manual_override_by",
            "updated_at",
        )
    )

    _refresh_sale_totals(sale)

    return line

@transaction.atomic
def set_sale_total_override(
    *,
    sale,
    final_total_amount,
    manual_override_reason,
    manual_override_by,
):
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if sale.status != Sale.Status.OPEN:
        raise ValidationError(
            "Il totale può essere modificato solo a vendita aperta."
        )

    if sale.payments.exists():
        raise ValidationError(
            "Rimuovere i pagamenti prima di modificare "
            "il totale della vendita."
        )

    lines = list(
        sale.lines.select_for_update().order_by(
            "created_at",
            "id",
        )
    )

    if not lines:
        raise ValidationError(
            "Non è possibile modificare il totale di una vendita vuota."
        )

    final_total_amount = _money(
        Decimal(str(final_total_amount))
    )

    if final_total_amount < 0:
        raise ValidationError(
            "Il totale finale non può essere negativo."
        )

    base_amounts = [
        _money(line.net_amount - line.total_override_share)
        for line in lines
    ]
    calculated_total = _money(
        sum(base_amounts, Decimal("0.00"))
    )

    if final_total_amount == calculated_total:
        for line, base_amount in zip(lines, base_amounts):
            line.total_override_share = Decimal("0.00")
            line.net_amount = base_amount
            line.discount_amount = max(
                _money(line.gross_amount - base_amount),
                Decimal("0.00"),
            )
            line.tax_amount = _included_tax(
                gross_amount=base_amount,
                tax_percentage=line.tax_percentage,
            )
            line.save(
                update_fields=(
                    "total_override_share",
                    "net_amount",
                    "discount_amount",
                    "tax_amount",
                    "updated_at",
                )
            )

        sale.manual_total_override_amount = None
        sale.manual_total_adjustment = Decimal("0.00")
        sale.manual_override_reason = ""
        sale.manual_override_by = None
        sale.save(
            update_fields=(
                "manual_total_override_amount",
                "manual_total_adjustment",
                "manual_override_reason",
                "manual_override_by",
                "updated_at",
            )
        )

        _refresh_sale_totals(sale)
        return sale

    if not manual_override_reason.strip():
        raise ValidationError(
            "La modifica manuale del totale richiede una motivazione."
        )

    if any(
        line.pricing_mode != SaleLine.PricingMode.STANDARD
        for line in lines
    ):
        raise ValidationError(
            "Non è possibile modificare manualmente il totale "
            "durante saldi o promozioni."
        )

    allocated_total = Decimal("0.00")

    for position, (line, base_amount) in enumerate(
        zip(lines, base_amounts)
    ):
        is_last = position == len(lines) - 1

        if is_last:
            allocated_amount = _money(
                final_total_amount - allocated_total
            )
        elif calculated_total == 0:
            allocated_amount = Decimal("0.00")
        else:
            allocated_amount = _money(
                final_total_amount
                * base_amount
                / calculated_total
            )

        allocated_total = _money(
            allocated_total + allocated_amount
        )

        line.total_override_share = _money(
            allocated_amount - base_amount
        )
        line.net_amount = allocated_amount
        line.discount_amount = max(
            _money(line.gross_amount - allocated_amount),
            Decimal("0.00"),
        )
        line.tax_amount = _included_tax(
            gross_amount=allocated_amount,
            tax_percentage=line.tax_percentage,
        )
        line.save(
            update_fields=(
                "total_override_share",
                "net_amount",
                "discount_amount",
                "tax_amount",
                "updated_at",
            )
        )

    sale.manual_total_override_amount = final_total_amount
    sale.manual_override_reason = manual_override_reason.strip()
    sale.manual_override_by = manual_override_by
    sale.save(
        update_fields=(
            "manual_total_override_amount",
            "manual_override_reason",
            "manual_override_by",
            "updated_at",
        )
    )

    _refresh_sale_totals(sale)

    return sale

def get_open_sale_stock_warning(
    *,
    variant,
    location,
):
    available_quantity = (
        StockBalance.objects.filter(
            variant=variant,
            location=location,
        )
        .values_list("quantity_on_hand", flat=True)
        .first()
        or 0
    )

    open_sale_quantity = (
        SaleLine.objects.filter(
            variant=variant,
            sale__location=location,
            sale__status=Sale.Status.OPEN,
        )
        .aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    return {
        "variant_id": variant.pk,
        "location_id": location.pk,
        "available_quantity": available_quantity,
        "open_sale_quantity": open_sale_quantity,
        "has_insufficient_stock_warning": (
            open_sale_quantity > available_quantity
        ),
    }

@transaction.atomic
def add_sale_payment(
    *,
    sale,
    method,
    amount,
    created_by,
    cash_received_amount=None,
    transaction_reference="",
    source_type="",
    source_id=None,
    occurred_at=None,
):
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if sale.status != Sale.Status.OPEN:
        raise ValidationError(
            "I pagamenti possono essere modificati "
            "solo a vendita aperta."
        )

    valid_methods = {
        choice.value for choice in SalePayment.Method
    }
    if method not in valid_methods:
        raise ValidationError(
            "Il metodo di pagamento non è valido."
        )

    amount = _money(Decimal(str(amount)))

    if amount <= 0:
        raise ValidationError(
            "L'importo del pagamento deve essere maggiore di zero."
        )

    existing_payments = list(
        sale.payments.select_for_update().all()
    )
    already_paid = _money(
        sum(
            (payment.amount for payment in existing_payments),
            Decimal("0.00"),
        )
    )

    if already_paid + amount > sale.final_total_amount:
        raise ValidationError(
            "Il totale dei pagamenti supera "
            "il totale della vendita."
        )

    cash_change_amount = None

    if method == SalePayment.Method.CASH:
        if cash_received_amount is None:
            raise ValidationError(
                "Per i contanti è necessario indicare "
                "l'importo ricevuto."
            )

        cash_received_amount = _money(
            Decimal(str(cash_received_amount))
        )

        if cash_received_amount < amount:
            raise ValidationError(
                "Il contante ricevuto non può essere "
                "inferiore all'importo del pagamento."
            )

        cash_change_amount = _money(
            cash_received_amount - amount
        )
    else:
        cash_received_amount = None

    return SalePayment.objects.create(
        sale=sale,
        method=method,
        amount=amount,
        cash_received_amount=cash_received_amount,
        cash_change_amount=cash_change_amount,
        transaction_reference=transaction_reference.strip(),
        source_type=source_type.strip(),
        source_id=source_id,
        occurred_at=occurred_at or timezone.now(),
        created_by=created_by,
    )

@transaction.atomic
def confirm_sale(
    *,
    sale,
    confirmed_by,
    confirmed_at=None,
):
    sale = (
        Sale.objects.select_for_update(of=("self",))
        .select_related(
            "cash_session",
            "cash_session__cash_register",
        )
        .get(pk=sale.pk)
    )

    if sale.status != Sale.Status.OPEN:
        raise ValidationError(
            "Può essere confermata solo una vendita aperta."
        )

    lines = list(
        sale.lines.select_for_update()
        .select_related("variant")
        .order_by("created_at", "id")
    )

    if not lines:
        raise ValidationError(
            "Non è possibile confermare una vendita vuota."
        )

    if sale.channel == Sale.Channel.POS:
        if sale.cash_session_id is None:
            raise ValidationError(
                "La vendita al banco richiede una sessione di cassa."
            )

        if sale.cash_session.status != CashSession.Status.OPEN:
            raise ValidationError(
                "La sessione di cassa non è aperta."
            )

        if (
            sale.cash_session.cash_register.location_id
            != sale.location_id
        ):
            raise ValidationError(
                "La cassa e la vendita appartengono "
                "a ubicazioni differenti."
            )

    _refresh_sale_totals(sale)

    payments = list(
        sale.payments.select_for_update().all()
    )
    paid_amount = _money(
        sum(
            (payment.amount for payment in payments),
            Decimal("0.00"),
        )
    )

    if paid_amount != sale.final_total_amount:
        raise ValidationError(
            "Il totale dei pagamenti deve coincidere "
            "con il totale finale della vendita."
        )

    confirmed_at = confirmed_at or timezone.now()
    sale_number = _next_sale_number(
        occurred_at=confirmed_at
    )

    for line in lines:
        movement = post_stock_movement(
            variant=line.variant,
            location=sale.location,
            movement_type=StockMovement.Type.SALE,
            quantity_delta=-line.quantity,
            occurred_at=confirmed_at,
            source_type="sales.Sale",
            source_id=sale.id,
            reference_number=sale_number,
            created_by=confirmed_by,
        )

        line.unit_cost_snapshot = movement.unit_cost
        line.total_cost_amount = _money(
            movement.unit_cost * Decimal(line.quantity)
        )
        line.save(
            update_fields=(
                "unit_cost_snapshot",
                "total_cost_amount",
                "updated_at",
            )
        )

    sale.number = sale_number
    sale.status = Sale.Status.CONFIRMED
    sale.confirmed_at = confirmed_at
    sale.confirmed_by = confirmed_by
    sale.total_cost_amount = _money(
        sum(
            (
                line.total_cost_amount
                for line in lines
            ),
            Decimal("0.00"),
        )
    )
    sale.save(
        update_fields=(
            "number",
            "status",
            "confirmed_at",
            "confirmed_by",
            "total_cost_amount",
            "updated_at",
        )
    )

    return sale
