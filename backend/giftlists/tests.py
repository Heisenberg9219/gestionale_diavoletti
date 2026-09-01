from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Category, Product, ProductVariant, Size, SizeScale
from core.models import Location, ShopSettings, TaxRate
from inventory.models import StockBalance
from pricing.models import VariantSalePrice
from sales.models import Sale
from sales.services import set_sale_line
from vouchers.models import Voucher

from .models import GiftList, GiftListContribution
from .services import (
    add_contribution,
    authorize_reserved_stock_sale,
    close_gift_list,
    get_reserved_stock_warning,
    record_item_purchase,
    set_gift_list_item,
)


class GiftListServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="giftlists-test@example.com",
            password="test-password",
        )
        cls.location = Location.objects.create(
            code="GIFTLIST_TEST_LOCATION",
            name="Negozio test liste",
            type=Location.Type.SALES_FLOOR,
        )
        tax_rate = TaxRate.objects.create(
            code="GIFTLIST_TEST_VAT",
            name="IVA test liste",
            percentage="22.00",
        )
        category = Category.objects.create(
            code="GIFTLIST_TEST_CATEGORY",
            name="Categoria test liste",
        )
        scale = SizeScale.objects.create(
            code="GIFTLIST_TEST_SCALE",
            name="Scala test liste",
            scale_type=SizeScale.Type.ONE_SIZE,
        )
        size = Size.objects.create(
            size_scale=scale,
            code="GIFTLIST_TEST_SIZE",
            label="Taglia unica test",
        )
        product = Product.objects.create(
            code="GIFTLIST_TEST_PRODUCT",
            name="Prodotto test liste",
            category=category,
            tax_rate=tax_rate,
        )
        cls.variant = ProductVariant.objects.create(
            product=product,
            sku="GIFTLIST_TEST_SKU",
            size=size,
        )
        VariantSalePrice.objects.create(
            variant=cls.variant,
            amount="24.90",
            created_by=cls.user,
        )
        ShopSettings.objects.update_or_create(
            singleton_key=True,
            defaults={"shop_name": "I Diavoletti"},
        )

    def setUp(self):
        StockBalance.objects.update_or_create(
            variant=self.variant,
            location=self.location,
            defaults={"quantity_on_hand": 1},
        )

    def create_list(self, *, mode=GiftList.Mode.PRODUCTS):
        return GiftList.objects.create(
            code=f"LIST-{GiftList.objects.count() + 1}",
            list_type=(
                GiftList.Type.BIRTH
                if mode == GiftList.Mode.PRODUCTS
                else GiftList.Type.BIRTHDAY
            ),
            mode=mode,
            title="Lista di prova",
            beneficiary_first_name="Anna",
            beneficiary_last_name="Rossi",
            location=self.location,
            created_by=self.user,
        )

    def create_sale(self):
        return Sale.objects.create(
            location=self.location,
            opened_by=self.user,
        )

    def test_birth_list_cannot_use_contribution_mode(self):
        gift_list = GiftList(
            code="INVALID-BIRTH",
            list_type=GiftList.Type.BIRTH,
            mode=GiftList.Mode.CONTRIBUTIONS,
            title="Lista non valida",
            beneficiary_first_name="Anna",
            beneficiary_last_name="Rossi",
            location=self.location,
            created_by=self.user,
        )
        with self.assertRaises(ValidationError):
            gift_list.full_clean()

    def test_reserved_item_generates_sale_warning(self):
        gift_list = self.create_list()
        set_gift_list_item(
            gift_list=gift_list,
            variant=self.variant,
            requested_quantity=1,
            reserved_quantity=1,
            added_by=self.user,
        )
        warning = get_reserved_stock_warning(
            sale=self.create_sale(),
            variant=self.variant,
            quantity=1,
        )
        self.assertTrue(warning["requires_authorization"])
        self.assertEqual(warning["reserved_quantity"], 1)
        self.assertEqual(warning["affected_list_codes"], [gift_list.code])

    def test_sale_of_reserved_item_requires_explicit_authorization(self):
        gift_list = self.create_list()
        set_gift_list_item(
            gift_list=gift_list,
            variant=self.variant,
            requested_quantity=1,
            reserved_quantity=1,
            added_by=self.user,
        )
        sale = self.create_sale()
        with self.assertRaises(ValidationError):
            set_sale_line(sale=sale, variant=self.variant, quantity=1)

        authorization = authorize_reserved_stock_sale(
            sale=sale,
            variant=self.variant,
            quantity=1,
            reason="Il cliente conferma comunque l'acquisto",
            authorized_by=self.user,
        )
        line = set_sale_line(
            sale=sale,
            variant=self.variant,
            quantity=1,
            reserved_stock_authorization=authorization,
        )
        self.assertEqual(line.quantity, 1)

    def test_purchase_marks_list_item_quantity(self):
        gift_list = self.create_list()
        item = set_gift_list_item(
            gift_list=gift_list,
            variant=self.variant,
            requested_quantity=2,
            reserved_quantity=1,
            added_by=self.user,
        )
        sale = self.create_sale()
        line = set_sale_line(
            sale=sale,
            variant=self.variant,
            quantity=1,
            gift_list_item=item,
        )

        purchase = record_item_purchase(
            item=item,
            sale_line=line,
            quantity=1,
            recorded_by=self.user,
        )

        item.refresh_from_db()
        self.assertEqual(item.purchased_quantity, 1)
        self.assertEqual(purchase.sale_line, line)

    def test_contribution_list_closes_and_generates_voucher(self):
        gift_list = self.create_list(mode=GiftList.Mode.CONTRIBUTIONS)
        add_contribution(
            gift_list=gift_list,
            first_name="Mario",
            last_name="Bianchi",
            amount="20.00",
            payment_method=GiftListContribution.PaymentMethod.CASH,
            recorded_by=self.user,
        )
        add_contribution(
            gift_list=gift_list,
            first_name="Lucia",
            last_name="Verdi",
            amount="15.50",
            payment_method=GiftListContribution.PaymentMethod.CARD,
            recorded_by=self.user,
        )

        closed_list, voucher = close_gift_list(
            gift_list=gift_list,
            closed_by=self.user,
        )

        self.assertEqual(closed_list.status, GiftList.Status.CLOSED)
        self.assertEqual(voucher.voucher_type, Voucher.Type.GIFT_LIST)
        self.assertEqual(voucher.initial_amount, Decimal("35.50"))
        self.assertEqual(voucher.current_balance, Decimal("35.50"))
        self.assertEqual(voucher.source_id, gift_list.id)

    def test_empty_contribution_list_cannot_be_closed(self):
        gift_list = self.create_list(mode=GiftList.Mode.CONTRIBUTIONS)
        with self.assertRaises(ValidationError):
            close_gift_list(gift_list=gift_list, closed_by=self.user)

    def test_closed_list_rejects_new_contribution(self):
        gift_list = self.create_list(mode=GiftList.Mode.CONTRIBUTIONS)
        add_contribution(
            gift_list=gift_list,
            first_name="Mario",
            last_name="Bianchi",
            amount="10.00",
            payment_method=GiftListContribution.PaymentMethod.CASH,
            recorded_by=self.user,
        )
        close_gift_list(gift_list=gift_list, closed_by=self.user)
        with self.assertRaises(ValidationError):
            add_contribution(
                gift_list=gift_list,
                first_name="Luca",
                last_name="Neri",
                amount="5.00",
                payment_method=GiftListContribution.PaymentMethod.CASH,
                recorded_by=self.user,
            )
