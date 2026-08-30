import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import StockBalance, StockMovement, VariantInventoryCost


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