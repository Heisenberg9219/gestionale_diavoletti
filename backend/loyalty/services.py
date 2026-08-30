import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    IssuedLoyaltyReward,
    LoyaltyEarningActivation,
    LoyaltyPointMovement,
    LoyaltyRewardDefinition,
)


@transaction.atomic
def create_earning_activation(
    *,
    rule,
    valid_from,
    valid_until=None,
    created_by=None,
):
    if not rule.is_active:
        raise ValidationError("La regola di accumulo non è attiva.")

    if valid_until is not None and valid_until <= valid_from:
        raise ValidationError(
            "La data finale deve essere successiva a quella iniziale."
        )

    overlapping = LoyaltyEarningActivation.objects.select_for_update().filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=valid_from)
    )

    if valid_until is not None:
        overlapping = overlapping.filter(valid_from__lt=valid_until)

    if overlapping.exists():
        raise ValidationError(
            "Il periodo si sovrappone a un'altra attivazione."
        )

    return LoyaltyEarningActivation.objects.create(
        rule=rule,
        valid_from=valid_from,
        valid_until=valid_until,
        created_by=created_by,
    )


def get_earning_activation(at=None):
    at = at or timezone.now()

    return (
        LoyaltyEarningActivation.objects.select_related("rule")
        .filter(
            valid_from__lte=at,
            rule__is_active=True,
        )
        .filter(
            Q(valid_until__isnull=True) | Q(valid_until__gt=at)
        )
        .first()
    )


def calculate_earned_points(*, eligible_amount, activation):
    eligible_amount = Decimal(str(eligible_amount))

    if eligible_amount <= 0:
        return 0

    spend_block_amount = Decimal(
        str(activation.rule.spend_block_amount)
    )
    complete_blocks = int(
        eligible_amount // spend_block_amount
    )

    return complete_blocks * activation.rule.points_per_block


def get_customer_points_balance(*, customer):
    result = customer.loyalty_point_movements.aggregate(
        total=Sum("points_delta")
    )
    return result["total"] or 0


@transaction.atomic
def record_point_movement(
    *,
    customer,
    points_delta,
    movement_type,
    earning_activation=None,
    source_type="",
    source_id=None,
    occurred_at=None,
    notes="",
    created_by=None,
):
    if points_delta == 0:
        raise ValidationError("Il movimento punti non può essere zero.")

    if (
        movement_type == LoyaltyPointMovement.Type.EARNED
        and points_delta < 0
    ):
        raise ValidationError(
            "I punti guadagnati devono essere positivi."
        )

    if movement_type in {
        LoyaltyPointMovement.Type.RETURN_REVERSAL,
        LoyaltyPointMovement.Type.REWARD_REDEMPTION,
        LoyaltyPointMovement.Type.EXPIRATION,
    } and points_delta > 0:
        raise ValidationError(
            "Questo tipo di movimento richiede punti negativi."
        )

    if (
        movement_type == LoyaltyPointMovement.Type.EARNED
        and earning_activation is None
    ):
        raise ValidationError(
            "I punti guadagnati richiedono una regola attiva."
        )

    return LoyaltyPointMovement.objects.create(
        customer=customer,
        points_delta=points_delta,
        movement_type=movement_type,
        earning_activation=earning_activation,
        source_type=source_type,
        source_id=source_id,
        occurred_at=occurred_at or timezone.now(),
        notes=notes,
        created_by=created_by,
    )


@transaction.atomic
def issue_loyalty_reward(
    *,
    customer,
    definition,
    created_by=None,
    issued_at=None,
):
    customer = (
        type(customer).objects.select_for_update().get(pk=customer.pk)
    )
    definition = (
        LoyaltyRewardDefinition.objects.select_for_update()
        .get(pk=definition.pk)
    )

    if not definition.is_active:
        raise ValidationError("Il premio selezionato non è attivo.")

    current_balance = get_customer_points_balance(customer=customer)
    if current_balance < definition.points_cost:
        raise ValidationError(
            "Il cliente non dispone di punti sufficienti."
        )

    issued_at = issued_at or timezone.now()
    reward_id = uuid.uuid4()
    reward_code = f"LOY-{uuid.uuid4().hex[:12].upper()}"

    point_movement = record_point_movement(
        customer=customer,
        points_delta=-definition.points_cost,
        movement_type=LoyaltyPointMovement.Type.REWARD_REDEMPTION,
        source_type="ISSUED_LOYALTY_REWARD",
        source_id=reward_id,
        occurred_at=issued_at,
        notes=f"Generazione premio {definition.code}",
        created_by=created_by,
    )

    fixed_amount = None
    remaining_amount = None
    percentage = None

    if (
        definition.reward_type
        == LoyaltyRewardDefinition.Type.FIXED_AMOUNT_DISCOUNT
    ):
        fixed_amount = definition.fixed_amount
        remaining_amount = definition.fixed_amount
    else:
        percentage = definition.percentage

    return IssuedLoyaltyReward.objects.create(
        id=reward_id,
        customer=customer,
        definition=definition,
        code=reward_code,
        reward_type=definition.reward_type,
        points_spent=definition.points_cost,
        fixed_amount=fixed_amount,
        remaining_amount=remaining_amount,
        percentage=percentage,
        minimum_purchase_amount=definition.minimum_purchase_amount,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(
            days=definition.validity_days
        ),
        point_movement=point_movement,
        created_by=created_by,
    )