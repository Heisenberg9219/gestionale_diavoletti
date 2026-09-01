from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import RoleMetadata
from core.models import Location, ShopSettings
from expenses.models import Expense, ExpenseCategory
from vouchers.models import Voucher
from vouchers.services import issue_voucher

from .models import Notification
from .services import (
    archive_notification,
    create_notification,
    generate_expense_due_notifications,
    generate_voucher_expiry_notifications,
    mark_notification_read,
    resolve_notification,
)


class NotificationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(
            email="notification-owner@example.com",
            password="test-password",
        )
        cls.clerk = user_model.objects.create_user(
            email="notification-clerk@example.com",
            password="test-password",
        )
        cls.owner_group = Group.objects.create(name="Notification Owners")
        cls.clerk_group = Group.objects.create(name="Notification Clerks")
        RoleMetadata.objects.create(
            group=cls.owner_group,
            code="NOTIF_OWNER",
        )
        RoleMetadata.objects.create(
            group=cls.clerk_group,
            code="NOTIF_CLERK",
        )
        cls.owner.groups.add(cls.owner_group, cls.clerk_group)
        cls.clerk.groups.add(cls.clerk_group)
        cls.location = Location.objects.create(
            code="NOTIF_TEST_LOCATION",
            name="Negozio test notifiche",
            type=Location.Type.SALES_FLOOR,
        )
        cls.expense_category = ExpenseCategory.objects.create(
            code="NOTIF_UTILITIES",
            name="Utenze test notifiche",
        )
        ShopSettings.objects.update_or_create(
            singleton_key=True,
            defaults={"shop_name": "I Diavoletti"},
        )

    def create_basic_notification(self, **kwargs):
        values = {
            "notification_type": Notification.Type.SYSTEM,
            "priority": Notification.Priority.NORMAL,
            "title": "Notifica di prova",
            "message": "Messaggio di prova",
            "deduplication_key": "test:basic",
            "users": (self.owner,),
        }
        values.update(kwargs)
        return create_notification(**values)

    def test_group_recipients_are_expanded_without_duplicates(self):
        notification, created = self.create_basic_notification(
            users=(),
            groups=(self.owner_group, self.clerk_group),
        )

        self.assertTrue(created)
        self.assertEqual(notification.deliveries.count(), 2)
        owner_delivery = notification.deliveries.get(user=self.owner)
        self.assertEqual(
            owner_delivery.matched_role_codes,
            ["NOTIF_CLERK", "NOTIF_OWNER"],
        )

    def test_active_notification_is_deduplicated(self):
        first, first_created = self.create_basic_notification()
        second, second_created = self.create_basic_notification(
            title="Titolo aggiornato"
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.title, "Titolo aggiornato")
        self.assertEqual(Notification.objects.count(), 1)

    def test_same_event_can_notify_again_after_resolution(self):
        first, _ = self.create_basic_notification()
        resolve_notification(
            notification=first,
            resolved_by=self.owner,
            notes="Evento gestito",
        )
        second, created = self.create_basic_notification()

        self.assertTrue(created)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(Notification.objects.count(), 2)

    def test_read_and_archive_are_personal(self):
        notification, _ = self.create_basic_notification()
        delivery = notification.deliveries.get()

        mark_notification_read(delivery=delivery)
        delivery.refresh_from_db()
        self.assertTrue(delivery.is_read)
        self.assertFalse(delivery.is_archived)

        archive_notification(delivery=delivery)
        delivery.refresh_from_db()
        self.assertTrue(delivery.is_archived)

    def test_resolution_requires_notes_and_is_traced(self):
        notification, _ = self.create_basic_notification()
        with self.assertRaises(ValidationError):
            resolve_notification(
                notification=notification,
                resolved_by=self.owner,
                notes="",
            )

        resolve_notification(
            notification=notification,
            resolved_by=self.owner,
            notes="Problema risolto",
        )
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.RESOLVED)
        self.assertEqual(notification.resolution.notes, "Problema risolto")

    def test_expense_due_generator_is_deduplicated(self):
        expense = Expense.objects.create(
            category=self.expense_category,
            location=self.location,
            description="Bolletta in scadenza",
            document_date=date.today(),
            due_date=date.today() + timedelta(days=2),
            taxable_amount="100.00",
            tax_amount="22.00",
            total_amount="122.00",
            status=Expense.Status.OPEN,
            created_by=self.owner,
        )

        first = generate_expense_due_notifications(users=(self.owner,))
        second = generate_expense_due_notifications(users=(self.owner,))

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0].pk, second[0].pk)
        self.assertEqual(first[0].source_id, expense.pk)

    def test_overdue_expense_has_critical_priority(self):
        Expense.objects.create(
            category=self.expense_category,
            description="Bolletta scaduta",
            document_date=date.today() - timedelta(days=10),
            due_date=date.today() - timedelta(days=1),
            taxable_amount="10.00",
            tax_amount="2.20",
            total_amount="12.20",
            status=Expense.Status.OPEN,
            created_by=self.owner,
        )
        notification = generate_expense_due_notifications(
            users=(self.owner,)
        )[0]
        self.assertEqual(notification.priority, Notification.Priority.CRITICAL)

    def test_voucher_expiry_generator_only_uses_active_window(self):
        now = timezone.now()
        voucher = issue_voucher(
            voucher_type=Voucher.Type.GIFT_CARD,
            initial_amount="30.00",
            issued_by=self.owner,
            issued_at=now - timedelta(days=30),
            expires_at=now + timedelta(days=3),
        )
        issue_voucher(
            voucher_type=Voucher.Type.GIFT_CARD,
            initial_amount="30.00",
            issued_by=self.owner,
            issued_at=now,
            expires_at=now + timedelta(days=30),
        )

        notifications = generate_voucher_expiry_notifications(
            users=(self.owner,),
            now=now,
            days_ahead=7,
        )

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].source_id, voucher.pk)
