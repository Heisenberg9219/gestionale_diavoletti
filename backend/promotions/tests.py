from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from catalog.models import (
    Brand,
    Category,
    Product,
    ProductVariant,
    Season,
    Size,
    SizeScale,
)
from core.models import Location, TaxRate
from pricing.models import VariantSalePrice
from sales.models import Sale, SaleLine
from sales.services import set_sale_line

from .models import (
    CampaignOffer,
    OfferBrandScope,
    OfferCategoryScope,
    PromotionCampaign,
    PromotionCampaignActivation,
    PromotionRule,
    SalePromotionApplication,
    ScopeMode,
)
from .services import (
    activate_campaign,
    apply_offer_to_sale,
    calculate_promotion_group,
    end_campaign_activation,
    get_activation_performance,
    is_variant_eligible_for_offer,
    remove_offer_from_sale,
)


class PromotionCalculationTests(TestCase):
    def make_rule(self, **overrides):
        values = {
            "code": "TEST_RULE",
            "name": "Regola test",
            "rule_type": PromotionRule.Type.PERCENTAGE,
            "required_quantity": 1,
            "discounted_quantity": 1,
            "discount_percentage": Decimal("20.00"),
            "target_selection": PromotionRule.TargetSelection.ALL,
        }
        values.update(overrides)
        return PromotionRule(**values)

    def test_percentage_discount(self):
        rule = self.make_rule()

        result = calculate_promotion_group(
            rule=rule,
            unit_prices=["24.90"],
        )

        self.assertEqual(
            result["final_prices"],
            [Decimal("19.92")],
        )
        self.assertEqual(
            result["discount_amount"],
            Decimal("4.98"),
        )

    def test_cheapest_item_receives_percentage_discount(self):
        rule = self.make_rule(
            rule_type=PromotionRule.Type.CHEAPEST_PERCENTAGE,
            required_quantity=2,
            target_selection=PromotionRule.TargetSelection.CHEAPEST,
            discount_percentage=Decimal("50.00"),
        )

        result = calculate_promotion_group(
            rule=rule,
            unit_prices=["20.00", "10.00"],
        )

        self.assertEqual(
            result["final_prices"],
            [Decimal("20.00"), Decimal("5.00")],
        )
        self.assertEqual(result["target_indexes"], [1])

    def test_fixed_group_discount_is_applied_once(self):
        rule = self.make_rule(
            rule_type=PromotionRule.Type.FIXED_DISCOUNT,
            required_quantity=2,
            discounted_quantity=2,
            discount_percentage=None,
            fixed_discount_amount=Decimal("5.00"),
            fixed_discount_scope=(
                PromotionRule.FixedDiscountScope.PER_GROUP
            ),
        )

        result = calculate_promotion_group(
            rule=rule,
            unit_prices=["20.00", "10.00"],
        )

        self.assertEqual(
            sum(result["final_prices"]),
            Decimal("25.00"),
        )
        self.assertEqual(
            result["discount_amount"],
            Decimal("5.00"),
        )

    def test_operator_must_select_exact_target_quantity(self):
        rule = self.make_rule(
            rule_type=PromotionRule.Type.GROUP_FIXED_PRICE,
            required_quantity=3,
            discount_percentage=None,
            fixed_unit_price=Decimal("1.00"),
            target_selection=(
                PromotionRule.TargetSelection.OPERATOR_SELECTED
            ),
        )

        with self.assertRaises(ValidationError):
            calculate_promotion_group(
                rule=rule,
                unit_prices=["10.00", "12.00", "15.00"],
                operator_selected_indexes=[],
            )

        result = calculate_promotion_group(
            rule=rule,
            unit_prices=["10.00", "12.00", "15.00"],
            operator_selected_indexes=[1],
        )

        self.assertEqual(
            result["final_prices"],
            [
                Decimal("10.00"),
                Decimal("1.00"),
                Decimal("15.00"),
            ],
        )


class PromotionApplicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="promotions-test@example.com",
            password="test-password",
        )
        tax_rate = TaxRate.objects.create(
            code="PROMO_TEST_VAT",
            name="IVA test promozioni",
            percentage="22.00",
        )
        cls.category = Category.objects.create(
            code="PROMO_TEST_CATEGORY",
            name="Categoria test promozioni",
        )
        cls.brand = Brand.objects.create(
            code="PROMO_TEST_BRAND",
            name="Marca test promozioni",
        )
        cls.other_brand = Brand.objects.create(
            code="PROMO_TEST_OTHER_BRAND",
            name="Altra marca test",
        )
        season = Season.objects.create(
            code="PROMO_TEST_SEASON",
            name="Stagione test promozioni",
            season_type=Season.Type.AUTUMN_WINTER,
            year=2026,
        )
        size_scale = SizeScale.objects.create(
            code="PROMO_TEST_SCALE",
            name="Scala test promozioni",
            scale_type=SizeScale.Type.ONE_SIZE,
        )
        size = Size.objects.create(
            size_scale=size_scale,
            code="PROMO_TEST_SIZE",
            label="Taglia unica test promo",
        )
        first_product = Product.objects.create(
            code="PROMO_TEST_PRODUCT_1",
            name="Primo prodotto test promo",
            brand=cls.brand,
            category=cls.category,
            season=season,
            tax_rate=tax_rate,
        )
        second_product = Product.objects.create(
            code="PROMO_TEST_PRODUCT_2",
            name="Secondo prodotto test promo",
            brand=cls.other_brand,
            category=cls.category,
            season=season,
            tax_rate=tax_rate,
        )
        cls.first_variant = ProductVariant.objects.create(
            product=first_product,
            sku="PROMO_TEST_SKU_1",
            size=size,
        )
        cls.second_variant = ProductVariant.objects.create(
            product=second_product,
            sku="PROMO_TEST_SKU_2",
            size=size,
        )
        cls.location = Location.objects.create(
            code="PROMO_TEST_LOCATION",
            name="Negozio test promozioni",
            type=Location.Type.SALES_FLOOR,
        )
        VariantSalePrice.objects.create(
            variant=cls.first_variant,
            amount="20.00",
            created_by=cls.user,
        )
        VariantSalePrice.objects.create(
            variant=cls.second_variant,
            amount="10.00",
            created_by=cls.user,
        )

    def create_campaign(self, *, code="PROMO_TEST_CAMPAIGN"):
        return PromotionCampaign.objects.create(
            code=code,
            name=f"Campagna {code}",
            campaign_type=PromotionCampaign.Type.PROMOTION,
            created_by=self.user,
        )

    def activate(self, campaign):
        now = timezone.now()
        return activate_campaign(
            campaign=campaign,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=10),
            enabled_by=self.user,
        )

    def create_rule(self, **overrides):
        values = {
            "code": "PROMO_TEST_RULE",
            "name": "Regola applicazione test",
            "rule_type": PromotionRule.Type.PERCENTAGE,
            "required_quantity": 1,
            "discounted_quantity": 1,
            "discount_percentage": Decimal("20.00"),
            "target_selection": PromotionRule.TargetSelection.ALL,
        }
        values.update(overrides)
        rule = PromotionRule(**values)
        rule.full_clean()
        rule.save()
        return rule

    def create_offer(self, *, campaign, rule, code="TEST_OFFER"):
        return CampaignOffer.objects.create(
            campaign=campaign,
            rule=rule,
            code=code,
            name=f"Offerta {code}",
            created_by=self.user,
        )

    def create_sale_with_lines(self, *, include_second=False):
        sale = Sale.objects.create(
            location=self.location,
            opened_by=self.user,
        )
        first_line = set_sale_line(
            sale=sale,
            variant=self.first_variant,
            quantity=1,
        )
        second_line = None
        if include_second:
            second_line = set_sale_line(
                sale=sale,
                variant=self.second_variant,
                quantity=1,
            )
        return sale, first_line, second_line

    def test_overlapping_campaigns_cannot_both_be_activated(self):
        rule = self.create_rule()
        first_campaign = self.create_campaign(code="FIRST_CAMPAIGN")
        second_campaign = self.create_campaign(code="SECOND_CAMPAIGN")
        self.create_offer(
            campaign=first_campaign,
            rule=rule,
            code="FIRST_OFFER",
        )
        self.create_offer(
            campaign=second_campaign,
            rule=rule,
            code="SECOND_OFFER",
        )

        self.activate(first_campaign)

        with self.assertRaises(ValidationError):
            self.activate(second_campaign)

    def test_campaign_can_be_reused_after_previous_activation_ends(self):
        campaign = self.create_campaign()
        rule = self.create_rule()
        self.create_offer(campaign=campaign, rule=rule)

        first_activation = self.activate(campaign)
        end_campaign_activation(
            activation=first_activation,
            ended_by=self.user,
        )
        second_activation = self.activate(campaign)

        first_activation.refresh_from_db()
        self.assertEqual(
            first_activation.status,
            PromotionCampaignActivation.Status.ENDED,
        )
        self.assertEqual(second_activation.activation_number, 2)
        self.assertEqual(
            second_activation.configuration_snapshot["campaign"]["code"],
            campaign.code,
        )

    def test_brand_exclusion_wins_over_category_inclusion(self):
        campaign = self.create_campaign()
        rule = self.create_rule()
        offer = self.create_offer(campaign=campaign, rule=rule)
        OfferCategoryScope.objects.create(
            offer=offer,
            category=self.category,
            mode=ScopeMode.INCLUDE,
        )
        OfferBrandScope.objects.create(
            offer=offer,
            brand=self.brand,
            mode=ScopeMode.EXCLUDE,
        )

        self.assertFalse(
            is_variant_eligible_for_offer(
                offer=offer,
                variant=self.first_variant,
            )
        )
        self.assertTrue(
            is_variant_eligible_for_offer(
                offer=offer,
                variant=self.second_variant,
            )
        )

    def test_percentage_offer_is_applied_and_removed_with_history(self):
        campaign = self.create_campaign()
        rule = self.create_rule()
        offer = self.create_offer(campaign=campaign, rule=rule)
        self.activate(campaign)
        sale, line, _ = self.create_sale_with_lines()

        application = apply_offer_to_sale(
            sale=sale,
            offer=offer,
            selected_quantities={line.id: 1},
            applied_by=self.user,
        )

        sale.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(line.pricing_mode, SaleLine.PricingMode.PROMOTION)
        self.assertEqual(line.net_amount, Decimal("16.00"))
        self.assertEqual(application.total_discount_amount, Decimal("4.00"))
        self.assertEqual(sale.final_total_amount, Decimal("16.00"))

        remove_offer_from_sale(
            application=application,
            removed_by=self.user,
            removal_reason="Cambio scelta cliente",
        )

        application.refresh_from_db()
        sale.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(
            application.status,
            SalePromotionApplication.Status.REMOVED,
        )
        self.assertEqual(line.pricing_mode, SaleLine.PricingMode.STANDARD)
        self.assertEqual(line.net_amount, Decimal("20.00"))
        self.assertEqual(sale.final_total_amount, Decimal("20.00"))

    def test_cheapest_item_offer_updates_both_involved_lines(self):
        campaign = self.create_campaign()
        rule = self.create_rule(
            rule_type=PromotionRule.Type.CHEAPEST_PERCENTAGE,
            required_quantity=2,
            discount_percentage=Decimal("50.00"),
            target_selection=PromotionRule.TargetSelection.CHEAPEST,
        )
        offer = self.create_offer(campaign=campaign, rule=rule)
        self.activate(campaign)
        sale, first_line, second_line = self.create_sale_with_lines(
            include_second=True
        )

        application = apply_offer_to_sale(
            sale=sale,
            offer=offer,
            selected_quantities={
                first_line.id: 1,
                second_line.id: 1,
            },
            applied_by=self.user,
        )

        sale.refresh_from_db()
        first_line.refresh_from_db()
        second_line.refresh_from_db()
        self.assertEqual(first_line.net_amount, Decimal("20.00"))
        self.assertEqual(second_line.net_amount, Decimal("5.00"))
        self.assertEqual(application.total_discount_amount, Decimal("5.00"))
        self.assertEqual(sale.final_total_amount, Decimal("25.00"))

    def test_activation_performance_uses_historical_snapshots(self):
        campaign = self.create_campaign()
        rule = self.create_rule()
        offer = self.create_offer(campaign=campaign, rule=rule)
        activation = self.activate(campaign)
        sale, line, _ = self.create_sale_with_lines()
        apply_offer_to_sale(
            sale=sale,
            offer=offer,
            selected_quantities={line.id: 1},
            applied_by=self.user,
        )
        Sale.objects.filter(pk=sale.pk).update(
            status=Sale.Status.CONFIRMED,
            number="V-PROMO-TEST",
        )

        report = get_activation_performance(activation=activation)

        self.assertEqual(report["totals"]["sale_count"], 1)
        self.assertEqual(report["totals"]["units_involved"], 1)
        self.assertEqual(
            report["totals"]["discount_amount"],
            Decimal("4.00"),
        )
        self.assertEqual(report["by_brand"][0]["code"], self.brand.code)
