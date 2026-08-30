from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CustomerConsentEvent


@transaction.atomic
def record_consent_event(
    *,
    customer,
    purpose,
    action,
    channel,
    collected_by=None,
    ip_address=None,
    user_agent="",
    related_event=None,
    occurred_at=None,
):
    if action not in CustomerConsentEvent.Action.values:
        raise ValidationError("Azione di consenso non valida.")

    if channel not in CustomerConsentEvent.Channel.values:
        raise ValidationError("Canale di raccolta non valido.")

    if (
        action
        in {
            CustomerConsentEvent.Action.GRANTED,
            CustomerConsentEvent.Action.CONFIRMATION_REQUESTED,
            CustomerConsentEvent.Action.CONFIRMED,
        }
        and not purpose.is_active
    ):
        raise ValidationError("La finalità di consenso non è attiva.")

    if purpose.requires_double_opt_in:
        if action == CustomerConsentEvent.Action.GRANTED:
            raise ValidationError(
                "Questa finalità richiede richiesta e conferma double opt-in."
            )
    elif action in {
        CustomerConsentEvent.Action.CONFIRMATION_REQUESTED,
        CustomerConsentEvent.Action.CONFIRMED,
    }:
        raise ValidationError(
            "Questa finalità non richiede double opt-in."
        )

    if action == CustomerConsentEvent.Action.CONFIRMED:
        if related_event is None:
            raise ValidationError(
                "La conferma deve riferirsi a una richiesta."
            )

        related_event = (
            CustomerConsentEvent.objects.select_for_update()
            .select_related("customer", "purpose")
            .get(pk=related_event.pk)
        )

        if (
            related_event.action
            != CustomerConsentEvent.Action.CONFIRMATION_REQUESTED
        ):
            raise ValidationError(
                "L'evento collegato non è una richiesta di conferma."
            )

        if related_event.customer_id != customer.pk:
            raise ValidationError(
                "La richiesta appartiene a un altro cliente."
            )

        if related_event.purpose_id != purpose.pk:
            raise ValidationError(
                "La richiesta appartiene a un'altra finalità."
            )

        if CustomerConsentEvent.objects.filter(
            related_event=related_event,
            action=CustomerConsentEvent.Action.CONFIRMED,
        ).exists():
            raise ValidationError(
                "Questa richiesta è già stata confermata."
            )
    elif related_event is not None:
        raise ValidationError(
            "Solo una conferma può collegarsi a un evento precedente."
        )

    return CustomerConsentEvent.objects.create(
        customer=customer,
        purpose=purpose,
        action=action,
        notice_version=purpose.notice_version,
        notice_text=purpose.notice_text,
        occurred_at=occurred_at or timezone.now(),
        channel=channel,
        collected_by=collected_by,
        ip_address=ip_address,
        user_agent=user_agent,
        related_event=related_event,
    )


def has_active_consent(*, customer, purpose):
    latest_event = (
        CustomerConsentEvent.objects.filter(
            customer=customer,
            purpose=purpose,
            action__in=(
                CustomerConsentEvent.Action.GRANTED,
                CustomerConsentEvent.Action.CONFIRMED,
                CustomerConsentEvent.Action.WITHDRAWN,
            ),
        )
        .order_by("-occurred_at", "-created_at")
        .first()
    )

    if latest_event is None:
        return False

    return latest_event.action in {
        CustomerConsentEvent.Action.GRANTED,
        CustomerConsentEvent.Action.CONFIRMED,
    }