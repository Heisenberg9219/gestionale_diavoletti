from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.models import StockBalance
from notifications.models import Notification
from notifications.services import resolve_notification
from purchasing.models import PurchaseOrder
from suppliers.models import SupplierVariant

from .models import ReorderItem, ReorderItemChange, ReorderNotificationLink


def get_suggested_supplier(*, variant):
    preferred = SupplierVariant.objects.select_related("supplier").filter(
        variant=variant,
        is_active=True,
        is_preferred=True,
        supplier__is_active=True,
    ).first()
    if preferred is not None:
        return preferred
    links = list(
        SupplierVariant.objects.select_related("supplier").filter(
            variant=variant,
            is_active=True,
            supplier__is_active=True,
        )[:2]
    )
    return links[0] if len(links) == 1 else None


@transaction.atomic
def add_to_reorder_list(
    *, variant, location, added_by, requested_quantity=None, supplier=None,
    reason="", notes="", source_notification=None
):
    balance = (
        StockBalance.objects.select_for_update()
        .filter(
            variant=variant,
            location=location,
        )
        .order_by("pk")
        .first()
    )
    suggestion = get_suggested_supplier(variant=variant)
    if supplier is None and suggestion is not None:
        supplier = suggestion.supplier
    if requested_quantity is None:
        requested_quantity = (
            suggestion.minimum_order_quantity if suggestion is not None else 1
        )
    if requested_quantity <= 0:
        raise ValidationError("La quantità da riordinare deve essere positiva.")
    if supplier is not None and not SupplierVariant.objects.filter(
        variant=variant,
        supplier=supplier,
        is_active=True,
    ).exists():
        raise ValidationError("Il fornitore non è associato all'articolo.")

    reorder_item = (
        ReorderItem.objects.select_for_update()
        .filter(
            variant=variant,
            location=location,
            status=ReorderItem.Status.PENDING,
        )
        .order_by("pk")
        .first()
    )
    created = reorder_item is None
    if created:
        reorder_item = ReorderItem.objects.create(
            variant=variant,
            location=location,
            supplier=supplier,
            requested_quantity=requested_quantity,
            reason=(
                reason.strip()
                or ("Articolo esaurito" if balance and balance.quantity_on_hand == 0 else "")
            ),
            notes=notes.strip(),
            added_by=added_by,
        )

    if source_notification is not None:
        source_notification = Notification.objects.select_for_update().get(
            pk=source_notification.pk
        )
        if source_notification.notification_type != Notification.Type.STOCK_DEPLETED:
            raise ValidationError("La notifica non riguarda un articolo esaurito.")
        if balance is None or source_notification.source_id != balance.pk:
            raise ValidationError("La notifica non corrisponde alla giacenza indicata.")
        ReorderNotificationLink.objects.get_or_create(
            reorder_item=reorder_item,
            notification=source_notification,
        )
        if source_notification.status == Notification.Status.ACTIVE:
            resolve_notification(
                notification=source_notification,
                resolved_by=added_by,
                notes="Articolo aggiunto alla lista riordini",
            )
    return reorder_item, created


@transaction.atomic
def update_pending_reorder(
    *, reorder_item, requested_quantity, updated_by, supplier=None, notes=None
):
    reorder_item = ReorderItem.objects.select_for_update().get(pk=reorder_item.pk)
    if reorder_item.status != ReorderItem.Status.PENDING:
        raise ValidationError("Può essere modificato solo un riordino in attesa.")
    if requested_quantity <= 0:
        raise ValidationError("La quantità da riordinare deve essere positiva.")
    if supplier is not None and not SupplierVariant.objects.filter(
        variant=reorder_item.variant,
        supplier=supplier,
        is_active=True,
    ).exists():
        raise ValidationError("Il fornitore non è associato all'articolo.")
    ReorderItemChange.objects.create(
        reorder_item=reorder_item,
        previous_quantity=reorder_item.requested_quantity,
        new_quantity=requested_quantity,
        previous_supplier=reorder_item.supplier,
        new_supplier=supplier,
        changed_by=updated_by,
    )
    reorder_item.requested_quantity = requested_quantity
    reorder_item.supplier = supplier
    if notes is not None:
        reorder_item.notes = notes.strip()
    reorder_item.save(update_fields=(
        "requested_quantity", "supplier", "notes", "updated_at",
    ))
    return reorder_item


@transaction.atomic
def remove_from_reorder_list(*, reorder_item, removed_by, reason=""):
    reorder_item = ReorderItem.objects.select_for_update().get(pk=reorder_item.pk)
    if reorder_item.status != ReorderItem.Status.PENDING:
        raise ValidationError("Può essere rimosso solo un riordino in attesa.")
    reorder_item.status = ReorderItem.Status.REMOVED
    reorder_item.removed_at = timezone.now()
    reorder_item.removed_by = removed_by
    reorder_item.removal_reason = reason.strip()
    reorder_item.save(update_fields=(
        "status", "removed_at", "removed_by", "removal_reason", "updated_at",
    ))
    return reorder_item


@transaction.atomic
def link_reorder_to_purchase_order(
    *, reorder_item, purchase_order_line, ordered_by, ordered_at=None
):
    reorder_item = ReorderItem.objects.select_for_update().get(pk=reorder_item.pk)
    if reorder_item.status != ReorderItem.Status.PENDING:
        raise ValidationError("Il riordino non è più in attesa.")
    if purchase_order_line.order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError("L'ordine fornitore non è in bozza.")
    if purchase_order_line.variant_id != reorder_item.variant_id:
        raise ValidationError("La riga d'ordine riguarda un articolo diverso.")
    if (
        reorder_item.supplier_id is not None
        and purchase_order_line.order.supplier_id != reorder_item.supplier_id
    ):
        raise ValidationError("Il fornitore dell'ordine non coincide.")
    if purchase_order_line.quantity_ordered < reorder_item.requested_quantity:
        raise ValidationError("La quantità ordinata è inferiore a quella richiesta.")
    reorder_item.supplier = purchase_order_line.order.supplier
    reorder_item.purchase_order_line = purchase_order_line
    reorder_item.status = ReorderItem.Status.ORDERED
    reorder_item.ordered_at = ordered_at or timezone.now()
    reorder_item.ordered_by = ordered_by
    reorder_item.save(update_fields=(
        "supplier", "purchase_order_line", "status",
        "ordered_at", "ordered_by", "updated_at",
    ))
    return reorder_item


@transaction.atomic
def complete_reorder(*, reorder_item, completed_by, completed_at=None):
    reorder_item = ReorderItem.objects.select_for_update().get(pk=reorder_item.pk)
    if reorder_item.status != ReorderItem.Status.ORDERED:
        raise ValidationError("Può essere completato solo un riordino ordinato.")
    reorder_item.status = ReorderItem.Status.COMPLETED
    reorder_item.completed_at = completed_at or timezone.now()
    reorder_item.completed_by = completed_by
    reorder_item.save(update_fields=(
        "status", "completed_at", "completed_by", "updated_at",
    ))
    return reorder_item


def get_pending_reorders_by_supplier():
    groups = {}
    queryset = ReorderItem.objects.filter(
        status=ReorderItem.Status.PENDING
    ).select_related("supplier", "variant", "variant__product", "location")
    for item in queryset:
        key = item.supplier_id
        entry = groups.setdefault(
            key,
            {"supplier": item.supplier, "items": []},
        )
        entry["items"].append(item)
    return list(groups.values())
