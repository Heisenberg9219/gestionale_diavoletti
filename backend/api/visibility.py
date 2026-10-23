"""Dati riservati al titolare (costi d'acquisto, ricarichi, margini)."""

from .permissions import user_has_role


def can_see_costs(request):
    user = getattr(request, "user", None)
    return bool(user) and user_has_role(user, "Titolare")


class OwnerOnlyFieldsMixin:
    """Rimuove i campi elencati in ``owner_only_fields`` per chi non è titolare.

    I campi spariscono sia dalle risposte sia dai dati accettati in scrittura:
    un commesso che modifica un articolo non può leggere né sovrascrivere il
    prezzo d'acquisto impostato dal titolare.
    """

    owner_only_fields = ()

    def get_fields(self):
        fields = super().get_fields()
        if not can_see_costs(self.context.get("request")):
            for name in self.owner_only_fields:
                fields.pop(name, None)
        return fields
