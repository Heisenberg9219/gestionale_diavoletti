from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from customers.models import Customer

from .models import (
    IssuedLoyaltyReward,
    LoyaltyEarningRule,
    LoyaltyPointMovement,
    LoyaltyRewardDefinition,
)
from .services import (
    calculate_earned_points,
    create_earning_activation,
    get_customer_points_balance,
    issue_loyalty_reward,
    record_point_movement,
)


class LoyaltyServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Customer.objects.create(
            customer_code="LOYALTY_TEST_CUSTOMER",
            first_name="Mario",
            last_name="Rossi",
        )
        cls.rule = LoyaltyEarningRule.objects.create(
            code="LOYALTY_TEST_RULE",
            name="Un punto ogni dieci euro",
            spend_block_amount="10.00",
            points_per_block=1,
        )
        cls.fixed_reward = LoyaltyRewardDefinition.objects.create(
            code="LOYALTY_TEST_FIXED",
            name="Buono sconto dieci euro",
            reward_type=(
                LoyaltyRewardDefinition.Type.FIXED_AMOUNT_DISCOUNT
            ),
            points_cost=100,
            fixed_amount="10.00",
            validity_days=180,
        )
        cls.percentage_reward = LoyaltyRewardDefinition.objects.create(
            code="LOYALTY_TEST_PERCENTAGE",
            name="Sconto venti percento",
            reward_type=(
                LoyaltyRewardDefinition.Type.PERCENTAGE_DISCOUNT
            ),
            points_cost=200,
            percentage="20.00",
            validity_days=90,
        )

    def add_points(self, points):
        return record_point_movement(
            customer=self.customer,
            points_delta=points,
            movement_type=(
                LoyaltyPointMovement.Type.MANUAL_ADJUSTMENT
            ),
        )

    def test_points_are_calculated_using_complete_blocks(self):
        now = timezone.now()
        activation = create_earning_activation(
            rule=self.rule,
            valid_from=now,
        )

        points = calculate_earned_points(
            eligible_amount="29.90",
            activation=activation,
        )

        self.assertEqual(points, 2)

    def test_rule_can_be_reused_but_periods_cannot_overlap(self):
        now = timezone.now()

        create_earning_activation(
            rule=self.rule,
            valid_from=now - timedelta(days=30),
            valid_until=now - timedelta(days=20),
        )
        create_earning_activation(
            rule=self.rule,
            valid_from=now - timedelta(days=10),
            valid_until=now - timedelta(days=5),
        )

        with self.assertRaises(ValidationError):
            create_earning_activation(
                rule=self.rule,
                valid_from=now - timedelta(days=8),
                valid_until=now - timedelta(days=3),
            )

        self.assertEqual(self.rule.activations.count(), 2)

    def test_balance_can_become_negative_after_return(self):
        self.add_points(5)
        record_point_movement(
            customer=self.customer,
            points_delta=-7,
            movement_type=(
                LoyaltyPointMovement.Type.RETURN_REVERSAL
            ),
        )

        self.assertEqual(
            get_customer_points_balance(customer=self.customer),
            -2,
        )

    def test_reward_is_rejected_when_points_are_insufficient(self):
        with self.assertRaises(ValidationError):
            issue_loyalty_reward(
                customer=self.customer,
                definition=self.fixed_reward,
            )

        self.assertEqual(IssuedLoyaltyReward.objects.count(), 0)
        self.assertEqual(
            self.customer.loyalty_point_movements.count(),
            0,
        )

    def test_fixed_reward_is_issued_and_points_are_deducted(self):
        self.add_points(120)

        reward = issue_loyalty_reward(
            customer=self.customer,
            definition=self.fixed_reward,
        )

        self.assertEqual(reward.points_spent, 100)
        self.assertEqual(reward.fixed_amount, Decimal("10.00"))
        self.assertEqual(
            reward.remaining_amount,
            Decimal("10.00"),
        )
        self.assertIsNone(reward.percentage)
        self.assertEqual(
            get_customer_points_balance(customer=self.customer),
            20,
        )
        self.assertEqual(
            reward.point_movement.points_delta,
            -100,
        )

    def test_percentage_reward_is_issued_without_cash_value(self):
        self.add_points(250)

        reward = issue_loyalty_reward(
            customer=self.customer,
            definition=self.percentage_reward,
        )

        self.assertEqual(reward.percentage, Decimal("20.00"))
        self.assertIsNone(reward.fixed_amount)
        self.assertIsNone(reward.remaining_amount)
        self.assertEqual(
            get_customer_points_balance(customer=self.customer),
            50,
        )