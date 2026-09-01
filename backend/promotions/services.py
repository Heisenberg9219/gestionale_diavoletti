from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import connection, transaction

from sales.models import Sale, SaleLine
from sales.services import _included_tax, _refresh_sale_totals

from .models import (
    CampaignOffer,
    PromotionCampaign,
    PromotionCampaignActivation,
    SalePromotionAllocation,
    SalePromotionApplication,
    ScopeMode,
)

MONEY_QUANTIZER = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(
        MONEY_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def _select_target_indexes(
    *,
    rule,
    unit_prices,
    operator_selected_indexes=None,
):
    target_quantity = rule.discounted_quantity

    if rule.target_selection == rule.TargetSelection.ALL:
        return list(range(len(unit_prices)))

    if target_quantity > len(unit_prices):
        raise ValidationError(
            "Gli articoli da scontare superano "
            "quelli presenti nel gruppo."
        )

    if rule.target_selection == rule.TargetSelection.CHEAPEST:
        ordered = sorted(
            range(len(unit_prices)),
            key=lambda index: (unit_prices[index], index),
        )
        return ordered[:target_quantity]

    if (
        rule.target_selection
        == rule.TargetSelection.MOST_EXPENSIVE
    ):
        ordered = sorted(
            range(len(unit_prices)),
            key=lambda index: (
                -unit_prices[index],
                index,
            ),
        )
        return ordered[:target_quantity]

    selected = sorted(set(operator_selected_indexes or []))

    if len(selected) != target_quantity:
        raise ValidationError(
            "L'operatore deve selezionare esattamente "
            f"{target_quantity} articoli da scontare."
        )

    if any(
        index < 0 or index >= len(unit_prices)
        for index in selected
    ):
        raise ValidationError(
            "La selezione contiene un articolo non valido."
        )

    return selected

@transaction.atomic
def activate_campaign(
    *,
    campaign,
    valid_from,
    valid_until,
    enabled_by,
):
    campaign = PromotionCampaign.objects.select_for_update().get(
        pk=campaign.pk
    )

    if not campaign.is_active:
        raise ValidationError(
            "La campagna non è attiva e non può essere riutilizzata."
        )

    if valid_until <= valid_from:
        raise ValidationError(
            "La fine dell'attivazione deve essere successiva all'inizio."
        )

    active_offers = campaign.offers.filter(is_active=True)

    if not active_offers.exists():
        raise ValidationError(
            "La campagna deve contenere almeno un'offerta attiva."
        )

    inactive_rule_offers = active_offers.filter(
        rule__is_active=False
    )
    if inactive_rule_offers.exists():
        raise ValidationError(
            "Tutte le offerte attive devono usare regole attive."
        )

    for offer in active_offers.select_related("rule"):
        offer.rule.full_clean()

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            [7302026],
        )

    overlapping_activations = (
        PromotionCampaignActivation.objects.select_for_update()
        .filter(status=PromotionCampaignActivation.Status.ENABLED)
        .filter(
            valid_from__lt=valid_until,
            valid_until__gt=valid_from,
        )
    )

    if overlapping_activations.exists():
        raise ValidationError(
            "Il periodo si sovrappone a un'altra attivazione abilitata."
        )

    latest_number = (
        campaign.activations.order_by("-activation_number")
        .values_list("activation_number", flat=True)
        .first()
        or 0
    )

    activation = PromotionCampaignActivation.objects.create(
        campaign=campaign,
        activation_number=latest_number + 1,
        valid_from=valid_from,
        valid_until=valid_until,
        configuration_snapshot=_campaign_configuration_snapshot(
            campaign
        ),
        enabled_by=enabled_by,
    )

    return activation


@transaction.atomic
def end_campaign_activation(*, activation, ended_by, ended_at=None):
    activation = PromotionCampaignActivation.objects.select_for_update().get(
        pk=activation.pk
    )

    if activation.status != PromotionCampaignActivation.Status.ENABLED:
        raise ValidationError("Solo un'attivazione abilitata può terminare.")

    activation.status = PromotionCampaignActivation.Status.ENDED
    activation.ended_at = ended_at or timezone.now()
    activation.ended_by = ended_by
    activation.save(
        update_fields=("status", "ended_at", "ended_by", "updated_at")
    )
    return activation


@transaction.atomic
def cancel_campaign_activation(
    *,
    activation,
    cancelled_by,
    cancellation_reason,
    cancelled_at=None,
):
    activation = PromotionCampaignActivation.objects.select_for_update().get(
        pk=activation.pk
    )

    if activation.status != PromotionCampaignActivation.Status.ENABLED:
        raise ValidationError("Solo un'attivazione abilitata può essere annullata.")

    if not cancellation_reason.strip():
        raise ValidationError("L'annullamento richiede una motivazione.")

    activation.status = PromotionCampaignActivation.Status.CANCELLED
    activation.cancelled_at = cancelled_at or timezone.now()
    activation.cancelled_by = cancelled_by
    activation.cancellation_reason = cancellation_reason.strip()
    activation.save(
        update_fields=(
            "status",
            "cancelled_at",
            "cancelled_by",
            "cancellation_reason",
            "updated_at",
        )
    )
    return activation

def is_variant_eligible_for_offer(*, offer, variant):
    variant = (
        type(variant).objects.select_related(
            "product",
            "product__category",
            "product__brand",
            "product__season",
        )
        .get(pk=variant.pk)
    )
    product = variant.product

    supplier_ids = set(
        variant.supplier_links.filter(is_active=True)
        .values_list("supplier_id", flat=True)
    )

    dimensions = (
        (
            offer.category_scopes.all(),
            {product.category_id},
            "category_id",
        ),
        (
            offer.brand_scopes.all(),
            {product.brand_id} if product.brand_id else set(),
            "brand_id",
        ),
        (
            offer.season_scopes.all(),
            {product.season_id} if product.season_id else set(),
            "season_id",
        ),
        (
            offer.supplier_scopes.all(),
            supplier_ids,
            "supplier_id",
        ),
        (
            offer.product_scopes.all(),
            {product.id},
            "product_id",
        ),
        (
            offer.variant_scopes.all(),
            {variant.id},
            "variant_id",
        ),
    )

    for scopes, variant_values, field_name in dimensions:
        included_values = {
            getattr(scope, field_name)
            for scope in scopes
            if scope.mode == ScopeMode.INCLUDE
        }
        excluded_values = {
            getattr(scope, field_name)
            for scope in scopes
            if scope.mode == ScopeMode.EXCLUDE
        }

        if excluded_values & variant_values:
            return False

        if included_values and not (
            included_values & variant_values
        ):
            return False

    return True

def get_available_offers_for_variant(
    *,
    variant,
    at=None,
):
    at = at or timezone.now()

    activation = (
        PromotionCampaignActivation.objects.select_related("campaign")
        .filter(
            status=PromotionCampaignActivation.Status.ENABLED,
            valid_from__lte=at,
            valid_until__gt=at,
        )
        .order_by("valid_from")
        .first()
    )

    if activation is None:
        return []

    offers = (
        activation.campaign.offers.filter(
            is_active=True,
            rule__is_active=True,
        )
        .select_related(
            "campaign",
            "rule",
        )
        .prefetch_related(
            "category_scopes",
            "brand_scopes",
            "season_scopes",
            "supplier_scopes",
            "product_scopes",
            "variant_scopes",
        )
        .order_by("sort_order", "name")
    )

    return [
        offer
        for offer in offers
        if is_variant_eligible_for_offer(
            offer=offer,
            variant=variant,
        )
    ]

def calculate_promotion_group(
    *,
    rule,
    unit_prices,
    operator_selected_indexes=None,
):
    rule.full_clean()

    unit_prices = [_money(price) for price in unit_prices]

    if len(unit_prices) != rule.required_quantity:
        raise ValidationError(
            "Il gruppo deve contenere esattamente "
            f"{rule.required_quantity} articoli."
        )

    target_indexes = _select_target_indexes(
        rule=rule,
        unit_prices=unit_prices,
        operator_selected_indexes=operator_selected_indexes,
    )
    final_prices = list(unit_prices)

    percentage_types = {
        rule.Type.PERCENTAGE,
        rule.Type.CHEAPEST_PERCENTAGE,
    }
    fixed_price_types = {
        rule.Type.FIXED_PRICE,
        rule.Type.GROUP_FIXED_PRICE,
    }

    if rule.rule_type in percentage_types:
        multiplier = (
            Decimal("1.00")
            - rule.discount_percentage / Decimal("100.00")
        )

        for index in target_indexes:
            final_prices[index] = _money(
                unit_prices[index] * multiplier
            )

    elif rule.rule_type in fixed_price_types:
        for index in target_indexes:
            final_prices[index] = min(
                unit_prices[index],
                _money(rule.fixed_unit_price),
            )

    elif (
        rule.rule_type == rule.Type.FIXED_DISCOUNT
        and rule.fixed_discount_scope
        == rule.FixedDiscountScope.PER_ITEM
    ):
        for index in target_indexes:
            final_prices[index] = max(
                _money(
                    unit_prices[index]
                    - rule.fixed_discount_amount
                ),
                Decimal("0.00"),
            )

    elif rule.rule_type == rule.Type.FIXED_DISCOUNT:
        target_total = _money(
            sum(
                (unit_prices[index] for index in target_indexes),
                Decimal("0.00"),
            )
        )
        total_discount = min(
            _money(rule.fixed_discount_amount),
            target_total,
        )
        target_final_total = _money(
            target_total - total_discount
        )
        allocated_total = Decimal("0.00")

        for position, index in enumerate(target_indexes):
            is_last = position == len(target_indexes) - 1

            if is_last:
                allocated_price = _money(
                    target_final_total - allocated_total
                )
            elif target_total == 0:
                allocated_price = Decimal("0.00")
            else:
                allocated_price = _money(
                    target_final_total
                    * unit_prices[index]
                    / target_total
                )

            final_prices[index] = allocated_price
            allocated_total = _money(
                allocated_total + allocated_price
            )

    discount_amount = _money(
        sum(unit_prices, Decimal("0.00"))
        - sum(final_prices, Decimal("0.00"))
    )

    return {
        "original_prices": unit_prices,
        "final_prices": final_prices,
        "target_indexes": target_indexes,
        "discount_amount": discount_amount,
    }

def _rule_snapshot(rule):
    return {
        "code": rule.code,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "required_quantity": rule.required_quantity,
        "discounted_quantity": rule.discounted_quantity,
        "discount_percentage": (
            str(rule.discount_percentage)
            if rule.discount_percentage is not None
            else None
        ),
        "fixed_discount_amount": (
            str(rule.fixed_discount_amount)
            if rule.fixed_discount_amount is not None
            else None
        ),
        "fixed_discount_scope": rule.fixed_discount_scope,
        "fixed_unit_price": (
            str(rule.fixed_unit_price)
            if rule.fixed_unit_price is not None
            else None
        ),
        "repeatable": rule.repeatable,
        "grouping_mode": rule.grouping_mode,
        "target_selection": rule.target_selection,
    }


def _scope_snapshot(offer):
    scope_definitions = (
        ("categories", offer.category_scopes, "category_id"),
        ("brands", offer.brand_scopes, "brand_id"),
        ("seasons", offer.season_scopes, "season_id"),
        ("suppliers", offer.supplier_scopes, "supplier_id"),
        ("products", offer.product_scopes, "product_id"),
        ("variants", offer.variant_scopes, "variant_id"),
    )

    snapshot = {}

    for name, manager, field_name in scope_definitions:
        snapshot[name] = {
            ScopeMode.INCLUDE: [],
            ScopeMode.EXCLUDE: [],
        }

        for scope in manager.all():
            snapshot[name][scope.mode].append(
                str(getattr(scope, field_name))
            )

        snapshot[name][ScopeMode.INCLUDE].sort()
        snapshot[name][ScopeMode.EXCLUDE].sort()

    return snapshot


def _campaign_configuration_snapshot(campaign):
    offers = (
        campaign.offers.filter(is_active=True)
        .select_related("rule")
        .prefetch_related(
            "category_scopes",
            "brand_scopes",
            "season_scopes",
            "supplier_scopes",
            "product_scopes",
            "variant_scopes",
        )
        .order_by("sort_order", "name")
    )

    return {
        "campaign": {
            "code": campaign.code,
            "name": campaign.name,
            "campaign_type": campaign.campaign_type,
        },
        "offers": [
            {
                "code": offer.code,
                "name": offer.name,
                "rule": _rule_snapshot(offer.rule),
                "scope": _scope_snapshot(offer),
            }
            for offer in offers
        ],
    }

def _promotion_grouping_key(*, rule, sale_line):
    variant = sale_line.variant
    product = variant.product

    if rule.grouping_mode == rule.GroupingMode.SAME_PRODUCT:
        return ("product", product.id)

    if rule.grouping_mode == rule.GroupingMode.SAME_VARIANT:
        return ("variant", variant.id)

    if rule.grouping_mode == rule.GroupingMode.SAME_CATEGORY:
        return ("category", product.category_id)

    if rule.grouping_mode == rule.GroupingMode.SAME_BRAND:
        return ("brand", product.brand_id)

    return ("all", None)


def _build_promotion_groups(*, rule, selected_lines):
    buckets = defaultdict(list)

    for sale_line, selected_quantity in selected_lines:
        if selected_quantity <= 0:
            raise ValidationError(
                "La quantità selezionata deve essere positiva."
            )

        if selected_quantity > sale_line.quantity:
            raise ValidationError(
                "La quantità selezionata supera "
                "quella presente nella vendita."
            )

        key = _promotion_grouping_key(
            rule=rule,
            sale_line=sale_line,
        )

        for unit_number in range(selected_quantity):
            buckets[key].append(
                {
                    "sale_line": sale_line,
                    "unit_number": unit_number,
                    "price": _money(
                        sale_line.final_unit_price
                    ),
                }
            )

    groups = []

    for units in buckets.values():
        if len(units) % rule.required_quantity != 0:
            raise ValidationError(
                "Gli articoli selezionati non formano "
                "gruppi completi per questa promozione."
            )

        number_of_groups = (
            len(units) // rule.required_quantity
        )

        if not rule.repeatable and number_of_groups > 1:
            raise ValidationError(
                "Questa promozione può essere applicata "
                "una sola volta."
            )

        units.sort(
            key=lambda unit: (
                -unit["price"],
                str(unit["sale_line"].id),
                unit["unit_number"],
            )
        )

        for start in range(
            0,
            len(units),
            rule.required_quantity,
        ):
            groups.append(
                units[start:start + rule.required_quantity]
            )

    if not groups:
        raise ValidationError(
            "Non è stato selezionato alcun gruppo valido."
        )

    return groups

@transaction.atomic
def apply_offer_to_sale(
    *,
    sale,
    offer,
    selected_quantities,
    applied_by,
    operator_selected_quantities=None,
    applied_at=None,
):
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if sale.status != Sale.Status.OPEN:
        raise ValidationError(
            "La promozione può essere applicata "
            "solo a una vendita aperta."
        )

    if sale.payments.exists():
        raise ValidationError(
            "Rimuovere i pagamenti prima di modificare "
            "le promozioni della vendita."
        )

    if sale.manual_total_override_amount is not None:
        raise ValidationError(
            "Non è possibile combinare una promozione "
            "con un totale inserito manualmente."
        )

    offer = (
        CampaignOffer.objects.select_related(
            "campaign",
            "rule",
        )
        .prefetch_related(
            "category_scopes",
            "brand_scopes",
            "season_scopes",
            "supplier_scopes",
            "product_scopes",
            "variant_scopes",
        )
        .get(pk=offer.pk)
    )
    campaign = offer.campaign
    rule = offer.rule
    applied_at = applied_at or timezone.now()

    activation = (
        PromotionCampaignActivation.objects.select_for_update()
        .filter(
            campaign=campaign,
            status=PromotionCampaignActivation.Status.ENABLED,
            valid_from__lte=applied_at,
            valid_until__gt=applied_at,
        )
        .first()
    )

    if (
        not offer.is_active
        or not rule.is_active
        or activation is None
    ):
        raise ValidationError(
            "L'offerta non è attiva in questo momento."
        )

    rule.full_clean()

    normalized_quantities = {
        str(line_id): int(quantity)
        for line_id, quantity in selected_quantities.items()
    }

    if not normalized_quantities:
        raise ValidationError(
            "Selezionare almeno una riga della vendita."
        )

    lines = list(
        sale.lines.select_for_update(of=("self",))
        .select_related(
            "variant",
            "variant__product",
            "variant__product__category",
            "variant__product__brand",
            "variant__product__season",
        )
        .filter(id__in=normalized_quantities)
        .order_by("created_at", "id")
    )

    if len(lines) != len(normalized_quantities):
        raise ValidationError(
            "Una o più righe selezionate non appartengono "
            "alla vendita."
        )

    selected_lines = []

    for line in lines:
        if line.manual_unit_price is not None:
            raise ValidationError(
                "Una promozione non può essere applicata "
                "a un prezzo inserito manualmente."
            )

        if line.total_override_share != 0:
            raise ValidationError(
                "La riga contiene già una modifica "
                "manuale del totale."
            )

        if line.pricing_mode != SaleLine.PricingMode.STANDARD:
            raise ValidationError(
                "La riga contiene già un saldo "
                "o una promozione."
            )

        if line.promotion_allocations.filter(
            application__status=(
                SalePromotionApplication.Status.APPLIED
            )
        ).exists():
            raise ValidationError(
                "La riga è già coinvolta "
                "in un'altra promozione."
            )

        if not is_variant_eligible_for_offer(
            offer=offer,
            variant=line.variant,
        ):
            raise ValidationError(
                f"L'articolo {line.sku_snapshot} "
                "non è idoneo per questa offerta."
            )

        selected_lines.append(
            (
                line,
                normalized_quantities[str(line.id)],
            )
        )

    groups = _build_promotion_groups(
        rule=rule,
        selected_lines=selected_lines,
    )

    operator_remaining = {
        str(line_id): int(quantity)
        for line_id, quantity in (
            operator_selected_quantities or {}
        ).items()
    }

    if (
        rule.target_selection
        != rule.TargetSelection.OPERATOR_SELECTED
        and operator_remaining
    ):
        raise ValidationError(
            "Questa regola non richiede "
            "una selezione manuale del target."
        )

    application = SalePromotionApplication.objects.create(
        sale=sale,
        activation=activation,
        offer=offer,
        campaign_code_snapshot=campaign.code,
        campaign_name_snapshot=campaign.name,
        campaign_type_snapshot=campaign.campaign_type,
        offer_code_snapshot=offer.code,
        offer_name_snapshot=offer.name,
        rule_code_snapshot=rule.code,
        rule_name_snapshot=rule.name,
        rule_type_snapshot=rule.rule_type,
        rule_parameters_snapshot=_rule_snapshot(rule),
        scope_snapshot=_scope_snapshot(offer),
        applied_by=applied_by,
    )

    line_discounts = defaultdict(lambda: Decimal("0.00"))
    total_discount = Decimal("0.00")

    for group_number, group in enumerate(groups, start=1):
        operator_indexes = []

        if (
            rule.target_selection
            == rule.TargetSelection.OPERATOR_SELECTED
        ):
            for index, unit in enumerate(group):
                line_id = str(unit["sale_line"].id)

                if operator_remaining.get(line_id, 0) > 0:
                    operator_indexes.append(index)
                    operator_remaining[line_id] -= 1

                    if (
                        len(operator_indexes)
                        == rule.discounted_quantity
                    ):
                        break

        result = calculate_promotion_group(
            rule=rule,
            unit_prices=[
                unit["price"] for unit in group
            ],
            operator_selected_indexes=operator_indexes,
        )
        target_indexes = set(result["target_indexes"])
        group_lines = {}

        for index, unit in enumerate(group):
            line = unit["sale_line"]
            line_data = group_lines.setdefault(
                line.id,
                {
                    "line": line,
                    "quantity": 0,
                    "discounted_quantity": 0,
                    "original_amount": Decimal("0.00"),
                    "final_amount": Decimal("0.00"),
                },
            )
            line_data["quantity"] += 1
            line_data["original_amount"] += (
                result["original_prices"][index]
            )
            line_data["final_amount"] += (
                result["final_prices"][index]
            )

            if index in target_indexes:
                line_data["discounted_quantity"] += 1

        for line_data in group_lines.values():
            original_amount = _money(
                line_data["original_amount"]
            )
            final_amount = _money(
                line_data["final_amount"]
            )
            discount_amount = _money(
                original_amount - final_amount
            )

            SalePromotionAllocation.objects.create(
                application=application,
                sale_line=line_data["line"],
                sku_snapshot=line_data["line"].sku_snapshot,
                product_code_snapshot=(
                    line_data["line"].variant.product.code
                ),
                product_name_snapshot=(
                    line_data["line"].product_name_snapshot
                ),
                category_code_snapshot=(
                    line_data["line"].variant.product.category.code
                ),
                category_name_snapshot=(
                    line_data["line"].variant.product.category.name
                ),
                brand_code_snapshot=(
                    line_data["line"].variant.product.brand.code
                    if line_data["line"].variant.product.brand_id
                    else ""
                ),
                brand_name_snapshot=(
                    line_data["line"].variant.product.brand.name
                    if line_data["line"].variant.product.brand_id
                    else ""
                ),
                season_code_snapshot=(
                    line_data["line"].variant.product.season.code
                    if line_data["line"].variant.product.season_id
                    else ""
                ),
                season_name_snapshot=(
                    line_data["line"].variant.product.season.name
                    if line_data["line"].variant.product.season_id
                    else ""
                ),
                supplier_codes_snapshot=list(
                    line_data["line"].variant.supplier_links.filter(
                        is_active=True
                    )
                    .order_by("supplier__code")
                    .values_list("supplier__code", flat=True)
                ),
                group_number=group_number,
                quantity_in_group=line_data["quantity"],
                discounted_quantity=(
                    line_data["discounted_quantity"]
                ),
                original_amount=original_amount,
                final_amount=final_amount,
                discount_amount=discount_amount,
            )

            line_discounts[line_data["line"].id] += (
                discount_amount
            )
            total_discount += discount_amount

    if any(quantity != 0 for quantity in operator_remaining.values()):
        raise ValidationError(
            "La selezione manuale contiene quantità "
            "non utilizzate nei gruppi."
        )

    pricing_mode = (
        SaleLine.PricingMode.SALE
        if campaign.campaign_type == PromotionCampaign.Type.SALE
        else SaleLine.PricingMode.PROMOTION
    )

    for line in lines:
        discount_amount = _money(line_discounts[line.id])
        net_amount = _money(
            line.gross_amount - discount_amount
        )

        line.pricing_mode = pricing_mode
        line.discount_amount = discount_amount
        line.net_amount = net_amount
        line.final_unit_price = _money(
            net_amount / Decimal(line.quantity)
        )
        line.tax_amount = _included_tax(
            gross_amount=net_amount,
            tax_percentage=line.tax_percentage,
        )
        line.save(
            update_fields=(
                "pricing_mode",
                "discount_amount",
                "net_amount",
                "final_unit_price",
                "tax_amount",
                "updated_at",
            )
        )

    application.total_discount_amount = _money(
        total_discount
    )
    application.save(
        update_fields=(
            "total_discount_amount",
            "updated_at",
        )
    )

    _refresh_sale_totals(sale)

    return application

@transaction.atomic
def remove_offer_from_sale(
    *,
    application,
    removed_by,
    removal_reason,
    removed_at=None,
):
    application = (
        SalePromotionApplication.objects.select_for_update()
        .select_related("sale")
        .get(pk=application.pk)
    )
    sale = Sale.objects.select_for_update().get(
        pk=application.sale_id
    )

    if sale.status != Sale.Status.OPEN:
        raise ValidationError(
            "Una promozione può essere rimossa "
            "solo da una vendita aperta."
        )

    if application.status != application.Status.APPLIED:
        raise ValidationError(
            "La promozione non risulta applicata."
        )

    if sale.payments.exists():
        raise ValidationError(
            "Rimuovere i pagamenti prima di modificare "
            "le promozioni della vendita."
        )

    if not removal_reason.strip():
        raise ValidationError(
            "La rimozione richiede una motivazione."
        )

    line_ids = application.allocations.values_list(
        "sale_line_id",
        flat=True,
    ).distinct()

    lines = list(
        sale.lines.select_for_update()
        .filter(id__in=line_ids)
        .order_by("created_at", "id")
    )

    for line in lines:
        other_active_application_exists = (
            line.promotion_allocations.filter(
                application__status=(
                    SalePromotionApplication.Status.APPLIED
                )
            )
            .exclude(application=application)
            .exists()
        )

        if other_active_application_exists:
            raise ValidationError(
                "La riga è coinvolta anche in "
                "un'altra promozione attiva."
            )

        line.pricing_mode = SaleLine.PricingMode.STANDARD
        line.final_unit_price = line.base_unit_price
        line.discount_amount = Decimal("0.00")
        line.net_amount = line.gross_amount
        line.tax_amount = _included_tax(
            gross_amount=line.net_amount,
            tax_percentage=line.tax_percentage,
        )
        line.save(
            update_fields=(
                "pricing_mode",
                "final_unit_price",
                "discount_amount",
                "net_amount",
                "tax_amount",
                "updated_at",
            )
        )

    application.status = application.Status.REMOVED
    application.removed_at = removed_at or timezone.now()
    application.removed_by = removed_by
    application.removal_reason = removal_reason.strip()
    application.save(
        update_fields=(
            "status",
            "removed_at",
            "removed_by",
            "removal_reason",
            "updated_at",
        )
    )

    _refresh_sale_totals(sale)

    return application

@transaction.atomic
def remove_offer_from_sale(
    *,
    application,
    removed_by,
    removal_reason,
    removed_at=None,
):
    application = (
        SalePromotionApplication.objects.select_for_update()
        .select_related("sale")
        .get(pk=application.pk)
    )
    sale = Sale.objects.select_for_update().get(
        pk=application.sale_id
    )

    if sale.status != Sale.Status.OPEN:
        raise ValidationError(
            "Una promozione può essere rimossa "
            "solo da una vendita aperta."
        )

    if application.status != application.Status.APPLIED:
        raise ValidationError(
            "La promozione non risulta applicata."
        )

    if sale.payments.exists():
        raise ValidationError(
            "Rimuovere i pagamenti prima di modificare "
            "le promozioni della vendita."
        )

    if not removal_reason.strip():
        raise ValidationError(
            "La rimozione richiede una motivazione."
        )

    line_ids = application.allocations.values_list(
        "sale_line_id",
        flat=True,
    ).distinct()

    lines = list(
        sale.lines.select_for_update()
        .filter(id__in=line_ids)
        .order_by("created_at", "id")
    )

    for line in lines:
        other_active_application_exists = (
            line.promotion_allocations.filter(
                application__status=(
                    SalePromotionApplication.Status.APPLIED
                )
            )
            .exclude(application=application)
            .exists()
        )

        if other_active_application_exists:
            raise ValidationError(
                "La riga è coinvolta anche in "
                "un'altra promozione attiva."
            )

        line.pricing_mode = SaleLine.PricingMode.STANDARD
        line.final_unit_price = line.base_unit_price
        line.discount_amount = Decimal("0.00")
        line.net_amount = line.gross_amount
        line.tax_amount = _included_tax(
            gross_amount=line.net_amount,
            tax_percentage=line.tax_percentage,
        )
        line.save(
            update_fields=(
                "pricing_mode",
                "final_unit_price",
                "discount_amount",
                "net_amount",
                "tax_amount",
                "updated_at",
            )
        )

    application.status = application.Status.REMOVED
    application.removed_at = removed_at or timezone.now()
    application.removed_by = removed_by
    application.removal_reason = removal_reason.strip()
    application.save(
        update_fields=(
            "status",
            "removed_at",
            "removed_by",
            "removal_reason",
            "updated_at",
        )
    )

    _refresh_sale_totals(sale)

    return application


def get_activation_performance(*, activation):
    activation = PromotionCampaignActivation.objects.select_related(
        "campaign"
    ).get(pk=activation.pk)

    allocations = (
        SalePromotionAllocation.objects.filter(
            application__activation=activation,
            application__status=SalePromotionApplication.Status.APPLIED,
            application__sale__status=Sale.Status.CONFIRMED,
        )
        .select_related("application__sale", "sale_line")
        .order_by("created_at")
    )

    totals = {
        "sale_ids": set(),
        "application_ids": set(),
        "units_involved": 0,
        "units_discounted": 0,
        "gross_amount": Decimal("0.00"),
        "net_amount": Decimal("0.00"),
        "discount_amount": Decimal("0.00"),
        "cost_amount": Decimal("0.00"),
    }
    breakdowns = {
        "products": {},
        "brands": {},
        "categories": {},
    }

    def update_metrics(container, key, name, allocation, cost_amount):
        metrics = container.setdefault(
            key,
            {
                "code": key,
                "name": name,
                "units_involved": 0,
                "units_discounted": 0,
                "gross_amount": Decimal("0.00"),
                "net_amount": Decimal("0.00"),
                "discount_amount": Decimal("0.00"),
                "cost_amount": Decimal("0.00"),
            },
        )
        metrics["units_involved"] += allocation.quantity_in_group
        metrics["units_discounted"] += allocation.discounted_quantity
        metrics["gross_amount"] += allocation.original_amount
        metrics["net_amount"] += allocation.final_amount
        metrics["discount_amount"] += allocation.discount_amount
        metrics["cost_amount"] += cost_amount

    for allocation in allocations:
        cost_amount = _money(
            allocation.sale_line.unit_cost_snapshot
            * Decimal(allocation.quantity_in_group)
        )
        totals["sale_ids"].add(allocation.application.sale_id)
        totals["application_ids"].add(allocation.application_id)
        totals["units_involved"] += allocation.quantity_in_group
        totals["units_discounted"] += allocation.discounted_quantity
        totals["gross_amount"] += allocation.original_amount
        totals["net_amount"] += allocation.final_amount
        totals["discount_amount"] += allocation.discount_amount
        totals["cost_amount"] += cost_amount

        update_metrics(
            breakdowns["products"],
            allocation.product_code_snapshot,
            allocation.product_name_snapshot,
            allocation,
            cost_amount,
        )
        update_metrics(
            breakdowns["brands"],
            allocation.brand_code_snapshot or "NO_BRAND",
            allocation.brand_name_snapshot or "Senza marca",
            allocation,
            cost_amount,
        )
        update_metrics(
            breakdowns["categories"],
            allocation.category_code_snapshot,
            allocation.category_name_snapshot,
            allocation,
            cost_amount,
        )

    def finalize_metrics(metrics):
        metrics["gross_amount"] = _money(metrics["gross_amount"])
        metrics["net_amount"] = _money(metrics["net_amount"])
        metrics["discount_amount"] = _money(metrics["discount_amount"])
        metrics["cost_amount"] = _money(metrics["cost_amount"])
        metrics["margin_amount"] = _money(
            metrics["net_amount"] - metrics["cost_amount"]
        )
        return metrics

    result_totals = finalize_metrics(
        {
            key: value
            for key, value in totals.items()
            if key not in {"sale_ids", "application_ids"}
        }
    )
    result_totals["sale_count"] = len(totals["sale_ids"])
    result_totals["application_count"] = len(
        totals["application_ids"]
    )

    return {
        "activation_id": str(activation.id),
        "campaign_code": activation.campaign.code,
        "campaign_name": activation.campaign.name,
        "activation_number": activation.activation_number,
        "valid_from": activation.valid_from,
        "valid_until": activation.valid_until,
        "totals": result_totals,
        "by_product": [
            finalize_metrics(metrics)
            for metrics in breakdowns["products"].values()
        ],
        "by_brand": [
            finalize_metrics(metrics)
            for metrics in breakdowns["brands"].values()
        ],
        "by_category": [
            finalize_metrics(metrics)
            for metrics in breakdowns["categories"].values()
        ],
    }
