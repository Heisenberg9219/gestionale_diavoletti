from datetime import date, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from expenses.models import Expense, ExpenseCategory
from notifications.models import Notification, NotificationDelivery
from vouchers.services import issue_voucher


class GenerateNotificationsCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(email="notif-owner@example.com", password="x")
        cls.owner.groups.add(Group.objects.get(name="Titolare"))
        category = ExpenseCategory.objects.create(code="CMD", name="Utenze")
        Expense.objects.create(
            category=category, description="Bolletta", document_date=date.today(),
            due_date=date.today() + timedelta(days=2), taxable_amount="10.00", tax_amount="2.20",
            total_amount="12.20", status=Expense.Status.OPEN, notifications_enabled=True, created_by=cls.owner,
        )
        issue_voucher(voucher_type="GIFT_CARD", initial_amount="30.00", issued_by=cls.owner,
                      issued_at=timezone.now() - timedelta(days=30), expires_at=timezone.now() + timedelta(days=3),
                      notifications_enabled=True)

    def test_creates_expense_and_voucher_alerts_for_owners_once(self):
        out = StringIO()
        call_command("generate_notifications", stdout=out)
        call_command("generate_notifications", stdout=StringIO())
        self.assertIn("Spese in scadenza: 1", out.getvalue())
        self.assertIn("Buoni in scadenza: 1", out.getvalue())
        self.assertEqual(Notification.objects.filter(notification_type__in=("EXPENSE_DUE", "VOUCHER_EXPIRING")).count(), 2)
        self.assertEqual(NotificationDelivery.objects.filter(user=self.owner).count(), 2)
