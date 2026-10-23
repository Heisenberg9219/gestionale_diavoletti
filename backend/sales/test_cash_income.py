from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import Location
from giftlists.models import GiftList
from giftlists.services import add_contribution
from sales.models import CashRegister
from sales.services import close_cash_session, open_cash_session
from vouchers.services import issue_voucher


class CashIncomeOutsideSalesTests(TestCase):
    """Contributi liste regalo e buoni venduti in contanti entrano nella cassa."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(email="cash-income@example.com", password="x")
        cls.user.groups.add(Group.objects.get(name="Titolare"))
        cls.location = Location.objects.create(code="CASH-INC", name="Negozio", type="SALES_FLOOR")
        cls.register = CashRegister.objects.create(code="CASH-INC", name="Cassa 1", location=cls.location)

    def gift_list(self):
        return GiftList.objects.create(
            code="CASH-INC-LIST", list_type="BIRTHDAY", mode="CONTRIBUTIONS", title="Festa",
            beneficiary_first_name="Anna", beneficiary_last_name="Rossi",
            location=self.location, created_by=self.user,
        )

    def test_cash_contribution_and_voucher_sale_are_in_expected_cash(self):
        session = open_cash_session(cash_register=self.register, opened_by=self.user, opening_cash_amount="100.00")
        contribution = add_contribution(gift_list=self.gift_list(), first_name="Mario", last_name="Rossi",
                                        amount="30.00", payment_method="CASH", recorded_by=self.user)
        self.assertEqual(contribution.cash_session, session)
        card = add_contribution(gift_list=contribution.gift_list, first_name="Luca", last_name="Verdi",
                                amount="20.00", payment_method="CARD", recorded_by=self.user)
        self.assertIsNone(card.cash_session)
        voucher = issue_voucher(voucher_type="GIFT_CARD", initial_amount="50.00", issued_by=self.user, payment_method="CASH")
        self.assertEqual(voucher.cash_session, session)
        issue_voucher(voucher_type="GIFT_CARD", initial_amount="40.00", issued_by=self.user, payment_method="CARD")

        closed = close_cash_session(cash_session=session, counted_cash_amount="180.00", closed_by=self.user)
        self.assertEqual(closed.expected_cash_amount, Decimal("180.00"))
        self.assertEqual(closed.cash_difference, Decimal("0.00"))

    def test_cash_income_requires_an_open_cash_session(self):
        with self.assertRaises(ValidationError):
            add_contribution(gift_list=self.gift_list(), first_name="Mario", last_name="Rossi",
                             amount="30.00", payment_method="CASH", recorded_by=self.user)
        with self.assertRaises(ValidationError):
            issue_voucher(voucher_type="GIFT_CARD", initial_amount="50.00", issued_by=self.user, payment_method="CASH")

    def test_vouchers_without_payment_keep_working(self):
        voucher = issue_voucher(voucher_type="RETURN_CREDIT", initial_amount="10.00", issued_by=self.user)
        self.assertEqual(voucher.payment_method, "")
        self.assertIsNone(voucher.cash_session)
