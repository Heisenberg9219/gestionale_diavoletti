from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import Location

from .models import Expense, ExpenseCategory, ExpensePayment
from .services import (
    add_expense_payment,
    cancel_expense,
    get_expense_payment_total,
    open_expense,
)


class ExpenseServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="expenses-test@example.com",
            password="test-password",
        )
        cls.location = Location.objects.create(
            code="EXPENSE_TEST_LOCATION",
            name="Negozio test spese",
            type=Location.Type.SALES_FLOOR,
        )
        cls.category = ExpenseCategory.objects.create(
            code="UTILITIES",
            name="Utenze",
        )

    def create_expense(self, *, status=Expense.Status.DRAFT):
        return Expense.objects.create(
            category=self.category,
            location=self.location,
            description="Energia elettrica",
            document_number="BOL-001",
            document_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            taxable_amount="100.00",
            tax_amount="22.00",
            total_amount="122.00",
            status=status,
            created_by=self.user,
        )

    def test_expense_total_must_match_taxable_plus_tax(self):
        expense = self.create_expense()
        expense.total_amount = Decimal("121.00")
        with self.assertRaises(ValidationError):
            expense.full_clean()

    def test_due_date_cannot_precede_document_date(self):
        expense = self.create_expense()
        expense.due_date = expense.document_date - timedelta(days=1)
        with self.assertRaises(ValidationError):
            expense.full_clean()

    def test_draft_expense_can_be_opened_with_audit(self):
        expense = self.create_expense()
        open_expense(expense=expense, opened_by=self.user)

        expense.refresh_from_db()
        self.assertEqual(expense.status, Expense.Status.OPEN)
        change = expense.status_changes.get()
        self.assertEqual(change.previous_status, Expense.Status.DRAFT)
        self.assertEqual(change.new_status, Expense.Status.OPEN)

    def test_partial_and_final_payments_update_status(self):
        expense = self.create_expense(status=Expense.Status.OPEN)
        add_expense_payment(
            expense=expense,
            amount="50.00",
            payment_method=ExpensePayment.Method.BANK_TRANSFER,
            recorded_by=self.user,
        )
        expense.refresh_from_db()
        self.assertEqual(expense.status, Expense.Status.PARTIALLY_PAID)
        self.assertEqual(expense.paid_amount, Decimal("50.00"))

        add_expense_payment(
            expense=expense,
            amount="72.00",
            payment_method=ExpensePayment.Method.BANK_TRANSFER,
            recorded_by=self.user,
        )
        expense.refresh_from_db()
        self.assertEqual(expense.status, Expense.Status.PAID)
        self.assertEqual(expense.outstanding_amount, Decimal("0.00"))
        self.assertEqual(
            get_expense_payment_total(expense=expense),
            Decimal("122.00"),
        )

    def test_payment_cannot_exceed_outstanding_amount(self):
        expense = self.create_expense(status=Expense.Status.OPEN)
        with self.assertRaises(ValidationError):
            add_expense_payment(
                expense=expense,
                amount="123.00",
                payment_method=ExpensePayment.Method.CARD,
                recorded_by=self.user,
            )
        self.assertFalse(expense.payments.exists())

    def test_payment_is_immutable(self):
        expense = self.create_expense(status=Expense.Status.OPEN)
        payment = add_expense_payment(
            expense=expense,
            amount="20.00",
            payment_method=ExpensePayment.Method.CASH,
            recorded_by=self.user,
        )
        payment.reference = "Modifica vietata"
        with self.assertRaises(ValidationError):
            payment.save()
        with self.assertRaises(ValidationError):
            payment.delete()

    def test_paid_expense_cannot_be_cancelled(self):
        expense = self.create_expense(status=Expense.Status.OPEN)
        add_expense_payment(
            expense=expense,
            amount="20.00",
            payment_method=ExpensePayment.Method.CASH,
            recorded_by=self.user,
        )
        with self.assertRaises(ValidationError):
            cancel_expense(
                expense=expense,
                cancelled_by=self.user,
                reason="Tentativo non valido",
            )

    def test_unpaid_expense_can_be_cancelled_with_reason(self):
        expense = self.create_expense(status=Expense.Status.OPEN)
        cancel_expense(
            expense=expense,
            cancelled_by=self.user,
            reason="Documento duplicato",
        )
        expense.refresh_from_db()
        self.assertEqual(expense.status, Expense.Status.CANCELLED)
        self.assertEqual(expense.cancellation_reason, "Documento duplicato")
