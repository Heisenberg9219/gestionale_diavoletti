from datetime import timedelta

from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from expenses.models import Expense
from vouchers.models import Voucher

from .models import Notification, NotificationDelivery, NotificationResolution


def _resolve_recipients(*, users=(), groups=()):
    recipients = {}
    for user in users:
        if user.status == User.Status.ACTIVE:
            recipients.setdefault(user.pk, {"user": user, "roles": set()})
    for group in groups:
        role_code = (
            group.role_metadata.code
            if hasattr(group, "role_metadata")
            else group.name
        )
        for user in group.user_set.filter(status=User.Status.ACTIVE):
            entry = recipients.setdefault(
                user.pk,
                {"user": user, "roles": set()},
            )
            entry["roles"].add(role_code)
    return recipients.values()


@transaction.atomic
def create_notification(
    *, notification_type, priority, title, message, deduplication_key,
    users=(), groups=(), source_type="", source_id=None, action_path="",
    occurred_at=None
):
    recipients = list(_resolve_recipients(users=users, groups=groups))
    if not recipients:
        raise ValidationError("La notifica richiede almeno un destinatario attivo.")
    if not deduplication_key.strip():
        raise ValidationError("La chiave di deduplicazione è obbligatoria.")
    if bool(source_type.strip()) != bool(source_id):
        raise ValidationError("Tipo e identificativo della fonte devono essere abbinati.")

    notification = Notification.objects.select_for_update().filter(
        deduplication_key=deduplication_key.strip(),
        status=Notification.Status.ACTIVE,
    ).first()
    created = notification is None
    if created:
        notification = Notification.objects.create(
            notification_type=notification_type,
            priority=priority,
            title=title.strip(),
            message=message.strip(),
            deduplication_key=deduplication_key.strip(),
            source_type=source_type.strip(),
            source_id=source_id,
            action_path=action_path.strip(),
            occurred_at=occurred_at or timezone.now(),
        )
    else:
        notification.priority = priority
        notification.title = title.strip()
        notification.message = message.strip()
        notification.action_path = action_path.strip()
        notification.save(update_fields=(
            "priority", "title", "message", "action_path", "updated_at",
        ))

    for recipient in recipients:
        delivery, delivery_created = NotificationDelivery.objects.get_or_create(
            notification=notification,
            user=recipient["user"],
            defaults={"matched_role_codes": sorted(recipient["roles"])},
        )
        if not delivery_created:
            merged_roles = sorted(
                set(delivery.matched_role_codes) | recipient["roles"]
            )
            if merged_roles != delivery.matched_role_codes:
                delivery.matched_role_codes = merged_roles
                delivery.save(update_fields=("matched_role_codes", "updated_at"))
    return notification, created


@transaction.atomic
def mark_notification_read(*, delivery, read_at=None):
    delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery.pk)
    if delivery.read_at is None:
        delivery.read_at = read_at or timezone.now()
        delivery.save(update_fields=("read_at", "updated_at"))
    return delivery


@transaction.atomic
def archive_notification(*, delivery, archived_at=None):
    delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery.pk)
    now = archived_at or timezone.now()
    if delivery.read_at is None:
        delivery.read_at = now
    if delivery.archived_at is None:
        delivery.archived_at = now
    delivery.save(update_fields=("read_at", "archived_at", "updated_at"))
    return delivery


@transaction.atomic
def resolve_notification(*, notification, resolved_by, notes, resolved_at=None):
    notification = Notification.objects.select_for_update().get(pk=notification.pk)
    if notification.status != Notification.Status.ACTIVE:
        raise ValidationError("La notifica non è attiva.")
    if not notes.strip():
        raise ValidationError("La risoluzione richiede una nota.")
    resolved_at = resolved_at or timezone.now()
    notification.status = Notification.Status.RESOLVED
    notification.resolved_at = resolved_at
    notification.resolved_by = resolved_by
    notification.resolution_notes = notes.strip()
    notification.save(update_fields=(
        "status", "resolved_at", "resolved_by", "resolution_notes", "updated_at",
    ))
    NotificationResolution.objects.create(
        notification=notification,
        resolved_at=resolved_at,
        resolved_by=resolved_by,
        notes=notes.strip(),
    )
    return notification


def create_stock_depleted_notification(*, stock_balance, users=(), groups=()):
    return create_notification(
        notification_type=Notification.Type.STOCK_DEPLETED,
        priority=Notification.Priority.HIGH,
        title=f"Articolo esaurito: {stock_balance.variant.sku}",
        message=(
            f"La giacenza di {stock_balance.variant} presso "
            f"{stock_balance.location.name} è terminata."
        ),
        deduplication_key=f"stock-depleted:{stock_balance.pk}",
        users=users,
        groups=groups,
        source_type="inventory.StockBalance",
        source_id=stock_balance.pk,
        action_path=f"/inventory/stock/{stock_balance.pk}",
    )


def notify_stock_depleted_to_owners(*, stock_balance):
    owner_group = Group.objects.filter(
        role_metadata__code="OWNER",
        role_metadata__is_active=True,
    ).first()
    if (
        owner_group is None
        or not owner_group.user_set.filter(status=User.Status.ACTIVE).exists()
    ):
        return None
    notification, _ = create_stock_depleted_notification(
        stock_balance=stock_balance,
        groups=(owner_group,),
    )
    return notification


def generate_expense_due_notifications(
    *, users=(), groups=(), as_of=None, days_ahead=7
):
    as_of = as_of or timezone.localdate()
    cutoff = as_of + timedelta(days=days_ahead)
    notifications = []
    expenses = Expense.objects.filter(
        status__in=(Expense.Status.OPEN, Expense.Status.PARTIALLY_PAID),
        due_date__isnull=False,
        due_date__lte=cutoff,
    )
    for expense in expenses:
        priority = (
            Notification.Priority.CRITICAL
            if expense.due_date < as_of
            else Notification.Priority.HIGH
        )
        notification, _ = create_notification(
            notification_type=Notification.Type.EXPENSE_DUE,
            priority=priority,
            title=f"Scadenza spesa: {expense.description}",
            message=f"Scadenza {expense.due_date}; residuo {expense.outstanding_amount}.",
            deduplication_key=f"expense-due:{expense.pk}:{expense.due_date}",
            users=users,
            groups=groups,
            source_type="expenses.Expense",
            source_id=expense.pk,
            action_path=f"/expenses/{expense.pk}",
        )
        notifications.append(notification)
    return notifications


def generate_voucher_expiry_notifications(
    *, users=(), groups=(), now=None, days_ahead=7
):
    now = now or timezone.now()
    cutoff = now + timedelta(days=days_ahead)
    notifications = []
    for voucher in Voucher.objects.filter(
        status=Voucher.Status.ACTIVE,
        expires_at__gt=now,
        expires_at__lte=cutoff,
    ):
        notification, _ = create_notification(
            notification_type=Notification.Type.VOUCHER_EXPIRING,
            priority=Notification.Priority.NORMAL,
            title=f"Buono in scadenza: {voucher.code}",
            message=f"Il buono scade il {voucher.expires_at.date()}.",
            deduplication_key=f"voucher-expiry:{voucher.pk}:{voucher.expires_at.date()}",
            users=users,
            groups=groups,
            source_type="vouchers.Voucher",
            source_id=voucher.pk,
            action_path=f"/vouchers/{voucher.pk}",
        )
        notifications.append(notification)
    return notifications
