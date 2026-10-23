"""Genera gli avvisi periodici per i titolari.

Da eseguire una volta al giorno (cron sul server):
- spese in scadenza o scadute;
- buoni in scadenza nei prossimi 7 giorni;
- eventi delle liste regalo nei prossimi 7 giorni;
- riordini da gestire.

Vengono considerati solo i record con "notifiche attive". Gli avvisi già
presenti non vengono duplicati. Le notifiche sui prodotti esauriti restano
immediate (nascono alla conferma della vendita).
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from notifications.services import (
    generate_expense_due_notifications,
    generate_gift_list_notifications,
    generate_reorder_notifications,
    generate_voucher_expiry_notifications,
)


class Command(BaseCommand):
    help = "Genera gli avvisi su spese, buoni, liste regalo e riordini."

    def handle(self, *args, **options):
        owners = Group.objects.filter(
            role_metadata__code="OWNER",
            role_metadata__is_active=True,
        ).first()
        if owners is None:
            self.stderr.write("Ruolo titolare non trovato: nessun avviso generato.")
            return
        groups = (owners,)
        generators = (
            ("Spese in scadenza", generate_expense_due_notifications),
            ("Buoni in scadenza", generate_voucher_expiry_notifications),
            ("Eventi liste regalo", generate_gift_list_notifications),
            ("Riordini", generate_reorder_notifications),
        )
        for label, generate in generators:
            count = len(generate(groups=groups))
            self.stdout.write(f"{label}: {count}")
