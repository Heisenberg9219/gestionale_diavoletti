from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from inventory.models import (
    StockMovement,
    VariantInventoryCost,
)
from inventory.services import post_stock_movement
from pricing.models import VariantSalePrice
from .models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseCostAdjustment,
    SupplierInvoice,
)


@transaction.atomic
def send_purchase_order(*, order, sent_by=None, sent_at=None):
    order = (
        PurchaseOrder.objects.select_for_update()
        .prefetch_related("lines")
        .get(pk=order.pk)
    )

    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError(
            "Soltanto un ordine in bozza può essere inviato."
        )

    if not order.lines.exists():
        raise ValidationError(
            "L'ordine deve contenere almeno una riga."
        )

    order.status = PurchaseOrder.Status.SENT
    order.sent_at = sent_at or timezone.now()
    order.sent_by = sent_by
    order.save(
        update_fields=(
            "status",
            "sent_at",
            "sent_by",
            "updated_at",
        )
    )

    return order

def _set_variant_sale_price(
    *,
    variant,
    amount,
    valid_from,
    created_by=None,
):
    amount = Decimal(str(amount))

    current_price = (
        VariantSalePrice.objects.select_for_update(of=("self",))
        .filter(
            variant=variant,
            valid_until__isnull=True,
        )
        .order_by("-valid_from")
        .first()
    )

    if current_price is not None and current_price.amount == amount:
        return current_price

    if current_price is not None:
        if valid_from <= current_price.valid_from:
            raise ValidationError(
                "Il nuovo prezzo deve iniziare dopo quello attuale."
            )

        current_price.valid_until = valid_from
        current_price.save(
            update_fields=("valid_until", "updated_at")
        )

    return VariantSalePrice.objects.create(
        variant=variant,
        amount=amount,
        valid_from=valid_from,
        source=VariantSalePrice.Source.MANUAL,
        notes="Prezzo impostato dalla ricezione merce.",
        created_by=created_by,
    )


def _refresh_purchase_order_status(order):
    order_lines = list(order.lines.all())

    received_rows = (
        GoodsReceiptLine.objects.filter(
            purchase_order_line__order=order,
            receipt__status=GoodsReceipt.Status.CONFIRMED,
        )
        .values("purchase_order_line_id")
        .annotate(total_received=Sum("quantity_received"))
    )
    received_by_line = {
        row["purchase_order_line_id"]: row["total_received"]
        for row in received_rows
    }

    any_received = any(
        received_by_line.get(line.id, 0) > 0
        for line in order_lines
    )
    all_received = bool(order_lines) and all(
        received_by_line.get(line.id, 0) >= line.quantity_ordered
        for line in order_lines
    )

    if all_received:
        new_status = PurchaseOrder.Status.RECEIVED
    elif any_received:
        new_status = PurchaseOrder.Status.PARTIALLY_RECEIVED
    else:
        new_status = PurchaseOrder.Status.SENT

    if order.status != new_status:
        order.status = new_status
        order.save(update_fields=("status", "updated_at"))

@transaction.atomic
def confirm_goods_receipt(
    *,
    receipt,
    confirmed_by=None,
    confirmed_at=None,
):
    receipt = (
        GoodsReceipt.objects.select_for_update(of=("self",))
        .select_related(
            "supplier",
            "purchase_order",
            "destination_location",
        )
        .get(pk=receipt.pk)
    )

    if receipt.status != GoodsReceipt.Status.DRAFT:
        raise ValidationError(
            "Soltanto una ricezione in bozza può essere confermata."
        )

    lines = list(
        receipt.lines.select_for_update(of=("self",))
        .select_related(
            "variant",
            "purchase_order_line",
            "purchase_order_line__order",
        )
    )

    if not lines:
        raise ValidationError(
            "La ricezione deve contenere almeno una riga."
        )

    purchase_order = None

    if receipt.purchase_order_id is not None:
        purchase_order = (
            PurchaseOrder.objects.select_for_update()
            .prefetch_related("lines")
            .get(pk=receipt.purchase_order_id)
        )

        if purchase_order.supplier_id != receipt.supplier_id:
            raise ValidationError(
                "Ordine e ricezione appartengono a fornitori diversi."
            )

        if purchase_order.status not in {
            PurchaseOrder.Status.SENT,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
        }:
            raise ValidationError(
                "L'ordine non è in uno stato ricevibile."
            )

    confirmed_at = confirmed_at or timezone.now()

    for line in lines:
        order_line = line.purchase_order_line

        if order_line is not None:
            if purchase_order is None:
                raise ValidationError(
                    "Una riga ordine richiede un ordine in testata."
                )

            if order_line.order_id != purchase_order.id:
                raise ValidationError(
                    "La riga appartiene a un altro ordine."
                )

            if order_line.variant_id != line.variant_id:
                raise ValidationError(
                    "La variante non corrisponde alla riga ordine."
                )

        post_stock_movement(
            variant=line.variant,
            location=receipt.destination_location,
            movement_type=StockMovement.Type.PURCHASE_RECEIPT,
            quantity_delta=line.quantity_received,
            unit_cost=line.unit_cost,
            occurred_at=receipt.received_at,
            source_type="GOODS_RECEIPT",
            source_id=receipt.id,
            reference_number=receipt.number,
            created_by=confirmed_by,
        )

        if line.final_sale_price is not None:
            _set_variant_sale_price(
                variant=line.variant,
                amount=line.final_sale_price,
                valid_from=confirmed_at,
                created_by=confirmed_by,
            )

    receipt.status = GoodsReceipt.Status.CONFIRMED
    receipt.confirmed_at = confirmed_at
    receipt.confirmed_by = confirmed_by
    receipt.save(
        update_fields=(
            "status",
            "confirmed_at",
            "confirmed_by",
            "updated_at",
        )
    )

    if purchase_order is not None:
        _refresh_purchase_order_status(purchase_order)

    return receipt

def _apply_invoice_cost_adjustment(invoice_line):
    inventory_cost, _ = VariantInventoryCost.objects.get_or_create(
        variant=invoice_line.variant,
    )
    inventory_cost = VariantInventoryCost.objects.select_for_update().get(
        pk=inventory_cost.pk,
    )

    receipt_line = invoice_line.receipt_line
    if receipt_line is not None and receipt_line.unit_cost is not None:
        previous_unit_cost = receipt_line.unit_cost
    else:
        previous_unit_cost = (
            inventory_cost.weighted_average_unit_cost
        )

    final_unit_cost = invoice_line.final_unit_cost
    unit_cost_delta = final_unit_cost - previous_unit_cost

    quantity_invoiced = invoice_line.quantity_invoiced
    remaining_quantity = min(
        quantity_invoiced,
        inventory_cost.total_quantity,
    )
    sold_quantity = quantity_invoiced - remaining_quantity

    total_cost_delta = (
        Decimal(quantity_invoiced) * unit_cost_delta
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    inventory_value_delta = (
        Decimal(remaining_quantity) * unit_cost_delta
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    sold_cost_delta = (
        Decimal(sold_quantity) * unit_cost_delta
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    if remaining_quantity > 0:
        new_inventory_value = (
            inventory_cost.inventory_value
            + inventory_value_delta
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        if new_inventory_value < 0:
            raise ValidationError(
                "La rettifica renderebbe negativo il valore "
                "del magazzino."
            )

        new_weighted_cost = (
            new_inventory_value
            / Decimal(inventory_cost.total_quantity)
        ).quantize(
            Decimal("0.0001"),
            rounding=ROUND_HALF_UP,
        )

        inventory_cost.inventory_value = new_inventory_value
        inventory_cost.weighted_average_unit_cost = new_weighted_cost
        inventory_cost.save(
            update_fields=(
                "inventory_value",
                "weighted_average_unit_cost",
                "updated_at",
            )
        )

    return PurchaseCostAdjustment.objects.create(
        invoice_line=invoice_line,
        variant=invoice_line.variant,
        quantity_invoiced=quantity_invoiced,
        previous_unit_cost=previous_unit_cost,
        final_unit_cost=final_unit_cost,
        total_cost_delta=total_cost_delta,
        remaining_quantity_affected=remaining_quantity,
        inventory_value_delta=inventory_value_delta,
        sold_quantity_affected=sold_quantity,
        sold_cost_delta=sold_cost_delta,
    )

@transaction.atomic
def confirm_supplier_invoice(
    *,
    invoice,
    confirmed_by=None,
    confirmed_at=None,
):
    invoice = (
        SupplierInvoice.objects.select_for_update()
        .select_related("supplier")
        .get(pk=invoice.pk)
    )

    if invoice.status != SupplierInvoice.Status.DRAFT:
        raise ValidationError(
            "Soltanto una fattura in bozza può essere confermata."
        )

    lines = list(
        invoice.lines.select_for_update(of=("self",))
        .select_related(
            "variant",
            "receipt_line",
            "receipt_line__receipt",
            "receipt_line__receipt__supplier",
        )
    )

    if not lines:
        raise ValidationError(
            "La fattura deve contenere almeno una riga."
        )

    receipt_links = list(
        invoice.receipt_links.select_for_update()
        .select_related("receipt", "receipt__supplier")
    )
    linked_receipt_ids = {
        link.receipt_id for link in receipt_links
    }

    for link in receipt_links:
        if link.receipt.supplier_id != invoice.supplier_id:
            raise ValidationError(
                "La fattura contiene un DDT di un altro fornitore."
            )

        if link.receipt.status != GoodsReceipt.Status.CONFIRMED:
            raise ValidationError(
                "Tutti i DDT collegati devono essere confermati."
            )

    taxable_total = sum(
        (line.taxable_amount for line in lines),
        Decimal("0.00"),
    )
    tax_total = sum(
        (line.tax_amount for line in lines),
        Decimal("0.00"),
    )
    invoice_total = sum(
        (line.total_amount for line in lines),
        Decimal("0.00"),
    )

    if taxable_total != invoice.taxable_amount:
        raise ValidationError(
            "L'imponibile delle righe non coincide con la testata."
        )

    if tax_total != invoice.tax_amount:
        raise ValidationError(
            "L'IVA delle righe non coincide con la testata."
        )

    if invoice_total != invoice.total_amount:
        raise ValidationError(
            "Il totale delle righe non coincide con la testata."
        )

    for line in lines:
        receipt_line = line.receipt_line

        if receipt_line is not None:
            if receipt_line.receipt_id not in linked_receipt_ids:
                raise ValidationError(
                    "La riga fattura usa un DDT non collegato."
                )

            if receipt_line.receipt.supplier_id != invoice.supplier_id:
                raise ValidationError(
                    "La riga proviene da un altro fornitore."
                )

            if (
                receipt_line.receipt.status
                != GoodsReceipt.Status.CONFIRMED
            ):
                raise ValidationError(
                    "La riga proviene da un DDT non confermato."
                )

            if receipt_line.variant_id != line.variant_id:
                raise ValidationError(
                    "La variante non coincide con la riga del DDT."
                )

        _apply_invoice_cost_adjustment(line)

    invoice.status = SupplierInvoice.Status.CONFIRMED
    invoice.confirmed_at = confirmed_at or timezone.now()
    invoice.confirmed_by = confirmed_by
    invoice.save(
        update_fields=(
            "status",
            "confirmed_at",
            "confirmed_by",
            "updated_at",
        )
    )

    return invoice
