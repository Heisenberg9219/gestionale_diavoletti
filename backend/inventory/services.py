import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from catalog.models import ProductVariant

from .models import (
    InventoryCountLine,
    InventoryCountSession,
    StockBalance,
    StockMovement,
    VariantInventoryCost,
)


INBOUND_TYPES = {
    StockMovement.Type.INITIAL_STOCK,
    StockMovement.Type.PURCHASE_RECEIPT,
    StockMovement.Type.CUSTOMER_RETURN,
    StockMovement.Type.TRANSFER_IN,
    StockMovement.Type.ADJUSTMENT_IN,
    StockMovement.Type.INVENTORY_GAIN,
}

OUTBOUND_TYPES = {
    StockMovement.Type.SALE,
    StockMovement.Type.SUPPLIER_RETURN,
    StockMovement.Type.TRANSFER_OUT,
    StockMovement.Type.ADJUSTMENT_OUT,
    StockMovement.Type.INVENTORY_LOSS,
}

TRANSFER_TYPES = {
    StockMovement.Type.TRANSFER_IN,
    StockMovement.Type.TRANSFER_OUT,
}

MONEY_QUANTIZER = Decimal("0.01")
COST_QUANTIZER = Decimal("0.0001")


@transaction.atomic
def post_stock_movement(
    *,
    variant,
    location,
    movement_type,
    quantity_delta,
    unit_cost=None,
    occurred_at=None,
    source_type="",
    source_id=None,
    reference_number="",
    transfer_group_id=None,
    notes="",
    created_by=None,
):
    if quantity_delta == 0:
        raise ValidationError("La quantità del movimento non può essere zero.")

    if movement_type in INBOUND_TYPES and quantity_delta < 0:
        raise ValidationError("Un movimento in entrata richiede quantità positiva.")

    if movement_type in OUTBOUND_TYPES and quantity_delta > 0:
        raise ValidationError("Un movimento in uscita richiede quantità negativa.")

    if movement_type in TRANSFER_TYPES and transfer_group_id is None:
        raise ValidationError(
            "Un trasferimento richiede un identificativo di collegamento."
        )

    if unit_cost is not None:
        unit_cost = Decimal(str(unit_cost))
        if unit_cost < 0:
            raise ValidationError("Il costo unitario non può essere negativo.")

    balance, _ = StockBalance.objects.get_or_create(
        variant=variant,
        location=location,
    )
    balance = StockBalance.objects.select_for_update().get(pk=balance.pk)

    new_location_quantity = balance.quantity_on_hand + quantity_delta
    if new_location_quantity < 0:
        raise ValidationError(
            "Movimento non consentito: la giacenza diventerebbe negativa."
        )

    inventory_cost, _ = VariantInventoryCost.objects.get_or_create(
        variant=variant,
    )
    inventory_cost = VariantInventoryCost.objects.select_for_update().get(
        pk=inventory_cost.pk,
    )

    movement_unit_cost = unit_cost

    if movement_type not in TRANSFER_TYPES:
        new_total_quantity = (
            inventory_cost.total_quantity + quantity_delta
        )
        if new_total_quantity < 0:
            raise ValidationError(
                "Movimento non consentito: la quantità totale "
                "diventerebbe negativa."
            )

        current_cost = inventory_cost.weighted_average_unit_cost

        if quantity_delta > 0:
            movement_unit_cost = (
                unit_cost if unit_cost is not None else current_cost
            )
            new_inventory_value = (
                inventory_cost.inventory_value
                + Decimal(quantity_delta) * movement_unit_cost
            ).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)

            if new_total_quantity > 0:
                new_weighted_cost = (
                    new_inventory_value / Decimal(new_total_quantity)
                ).quantize(COST_QUANTIZER, rounding=ROUND_HALF_UP)
            else:
                new_weighted_cost = current_cost
        else:
            movement_unit_cost = current_cost
            new_inventory_value = (
                inventory_cost.inventory_value
                + Decimal(quantity_delta) * current_cost
            ).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
            new_inventory_value = max(
                new_inventory_value,
                Decimal("0.00"),
            )
            new_weighted_cost = current_cost

        inventory_cost.total_quantity = new_total_quantity
        inventory_cost.inventory_value = new_inventory_value
        inventory_cost.weighted_average_unit_cost = new_weighted_cost
        inventory_cost.last_movement_at = occurred_at or timezone.now()
        inventory_cost.save(
            update_fields=(
                "total_quantity",
                "inventory_value",
                "weighted_average_unit_cost",
                "last_movement_at",
                "updated_at",
            )
        )
    elif movement_unit_cost is None:
        movement_unit_cost = inventory_cost.weighted_average_unit_cost

    balance.quantity_on_hand = new_location_quantity
    balance.save(update_fields=("quantity_on_hand", "updated_at"))

    return StockMovement.objects.create(
        variant=variant,
        location=location,
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        unit_cost=movement_unit_cost,
        occurred_at=occurred_at or timezone.now(),
        source_type=source_type,
        source_id=source_id,
        reference_number=reference_number,
        transfer_group_id=transfer_group_id,
        notes=notes,
        created_by=created_by,
    )

@transaction.atomic
def transfer_stock(
    *,
    variant,
    source_location,
    destination_location,
    quantity,
    occurred_at=None,
    reference_number="",
    notes="",
    created_by=None,
):
    if quantity <= 0:
        raise ValidationError(
            "La quantità da trasferire deve essere maggiore di zero."
        )

    if source_location.pk == destination_location.pk:
        raise ValidationError(
            "Origine e destinazione del trasferimento devono essere diverse."
        )

    transfer_group_id = uuid.uuid4()
    occurred_at = occurred_at or timezone.now()

    outgoing_movement = post_stock_movement(
        variant=variant,
        location=source_location,
        movement_type=StockMovement.Type.TRANSFER_OUT,
        quantity_delta=-quantity,
        occurred_at=occurred_at,
        reference_number=reference_number,
        transfer_group_id=transfer_group_id,
        notes=notes,
        created_by=created_by,
    )

    incoming_movement = post_stock_movement(
        variant=variant,
        location=destination_location,
        movement_type=StockMovement.Type.TRANSFER_IN,
        quantity_delta=quantity,
        unit_cost=outgoing_movement.unit_cost,
        occurred_at=occurred_at,
        reference_number=reference_number,
        transfer_group_id=transfer_group_id,
        notes=notes,
        created_by=created_by,
    )

    return outgoing_movement, incoming_movement


def _inventory_scope_queryset(session):
    queryset = ProductVariant.objects.filter(is_active=True)
    if session.scope == InventoryCountSession.Scope.FULL:
        return queryset

    scope_filter = Q()
    has_scope = False
    selectors = (
        (session.brands.exists(), Q(product__brand__in=session.brands.all())),
        (session.categories.exists(), Q(product__category__in=session.categories.all())),
        (session.seasons.exists(), Q(product__season__in=session.seasons.all())),
        (session.products.exists(), Q(product__in=session.products.all())),
        (session.variants.exists(), Q(pk__in=session.variants.all())),
    )
    for is_selected, selector in selectors:
        if is_selected:
            scope_filter |= selector
            has_scope = True
    if not has_scope:
        raise ValidationError(
            "Un inventario parziale richiede almeno un criterio di selezione."
        )
    return queryset.filter(scope_filter).distinct()


@transaction.atomic
def start_inventory_count(*, session):
    session = InventoryCountSession.objects.select_for_update().get(pk=session.pk)
    if session.status != InventoryCountSession.Status.DRAFT:
        raise ValidationError("Può essere avviato solo un inventario in bozza.")
    if session.lines.exists():
        raise ValidationError("La sessione contiene già righe di inventario.")

    variants = list(_inventory_scope_queryset(session).order_by("pk"))
    if not variants:
        raise ValidationError("La selezione non contiene articoli da inventariare.")

    variant_ids = [variant.pk for variant in variants]
    balances = {
        balance.variant_id: balance.quantity_on_hand
        for balance in StockBalance.objects.filter(
            location=session.location,
            variant_id__in=variant_ids,
        ).order_by()
    }
    costs = {
        cost.variant_id: cost.weighted_average_unit_cost
        for cost in VariantInventoryCost.objects.filter(
            variant_id__in=variant_ids,
        ).order_by()
    }
    lines = []
    for variant in variants:
        expected_quantity = balances.get(variant.pk, 0)
        unit_cost = costs.get(variant.pk, Decimal("0.0000"))
        expected_value = (
            Decimal(expected_quantity) * unit_cost
        ).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
        lines.append(InventoryCountLine(
            session=session,
            variant=variant,
            expected_quantity=expected_quantity,
            unit_cost_snapshot=unit_cost,
            expected_value=expected_value,
        ))
    InventoryCountLine.objects.bulk_create(lines)
    session.status = InventoryCountSession.Status.IN_PROGRESS
    session.started_at = timezone.now()
    session.save(update_fields=("status", "started_at", "updated_at"))
    return session


@transaction.atomic
def record_inventory_count(*, line, counted_quantity, counted_by, notes=None):
    line = (
        InventoryCountLine.objects.select_for_update()
        .select_related("session")
        .get(pk=line.pk)
    )
    if line.session.status != InventoryCountSession.Status.IN_PROGRESS:
        raise ValidationError("Il conteggio non è modificabile in questo stato.")
    if counted_quantity < 0:
        raise ValidationError("La quantità contata non può essere negativa.")

    difference = counted_quantity - line.expected_quantity
    counted_value = (
        Decimal(counted_quantity) * line.unit_cost_snapshot
    ).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    difference_value = (
        Decimal(difference) * line.unit_cost_snapshot
    ).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    line.counted_quantity = counted_quantity
    line.difference_quantity = difference
    line.counted_value = counted_value
    line.difference_value = difference_value
    line.counted_at = timezone.now()
    line.counted_by = counted_by
    if notes is not None:
        line.notes = notes.strip()
    line.save(update_fields=(
        "counted_quantity", "difference_quantity", "counted_value",
        "difference_value", "counted_at", "counted_by", "notes", "updated_at",
    ))
    return line


@transaction.atomic
def confirm_inventory_count(*, session, confirmed_by):
    session = InventoryCountSession.objects.select_for_update().get(pk=session.pk)
    if session.status != InventoryCountSession.Status.IN_PROGRESS:
        raise ValidationError("Può essere confermato solo un inventario in corso.")

    lines = list(
        InventoryCountLine.objects.select_for_update()
        .filter(session=session)
        .select_related("variant")
        .order_by("pk")
    )
    if not lines or any(line.counted_quantity is None for line in lines):
        raise ValidationError("Tutti gli articoli devono essere conteggiati.")

    balances = {
        balance.variant_id: balance.quantity_on_hand
        for balance in StockBalance.objects.select_for_update()
        .filter(
            location=session.location,
            variant_id__in=[line.variant_id for line in lines],
        )
        .order_by("pk")
    }
    changed_skus = [
        line.variant.sku
        for line in lines
        if balances.get(line.variant_id, 0) != line.expected_quantity
    ]
    if changed_skus:
        raise ValidationError(
            "Le giacenze sono cambiate durante il conteggio: "
            + ", ".join(changed_skus[:10])
        )

    confirmed_at = timezone.now()
    for line in lines:
        if line.difference_quantity == 0:
            continue
        movement_type = (
            StockMovement.Type.INVENTORY_GAIN
            if line.difference_quantity > 0
            else StockMovement.Type.INVENTORY_LOSS
        )
        movement = post_stock_movement(
            variant=line.variant,
            location=session.location,
            movement_type=movement_type,
            quantity_delta=line.difference_quantity,
            unit_cost=(
                line.unit_cost_snapshot
                if line.difference_quantity > 0
                else None
            ),
            occurred_at=confirmed_at,
            source_type="inventory.InventoryCountSession",
            source_id=session.pk,
            reference_number=session.code,
            notes=f"Rettifica da inventario {session.code}",
            created_by=confirmed_by,
        )
        line.adjustment_movement = movement
        line.save(update_fields=("adjustment_movement", "updated_at"))

    session.status = InventoryCountSession.Status.CONFIRMED
    session.confirmed_at = confirmed_at
    session.confirmed_by = confirmed_by
    session.save(update_fields=(
        "status", "confirmed_at", "confirmed_by", "updated_at",
    ))
    return session


@transaction.atomic
def cancel_inventory_count(*, session, cancelled_by):
    session = InventoryCountSession.objects.select_for_update().get(pk=session.pk)
    if session.status not in (
        InventoryCountSession.Status.DRAFT,
        InventoryCountSession.Status.IN_PROGRESS,
    ):
        raise ValidationError("Questa sessione non può essere annullata.")
    session.status = InventoryCountSession.Status.CANCELLED
    session.cancelled_at = timezone.now()
    session.cancelled_by = cancelled_by
    session.save(update_fields=(
        "status", "cancelled_at", "cancelled_by", "updated_at",
    ))
    return session
