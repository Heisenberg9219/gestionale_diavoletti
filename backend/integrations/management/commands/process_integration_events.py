from django.core.management.base import BaseCommand

from integrations.services import process_available_sync_events


class Command(BaseCommand):
    help = "Elabora gli eventi di sincronizzazione esterna disponibili."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        events = process_available_sync_events(limit=options["limit"])
        succeeded = sum(event.status == "SUCCEEDED" for event in events)
        failed = sum(event.status == "FAILED" for event in events)
        retrying = sum(event.status == "RETRY" for event in events)
        self.stdout.write(
            self.style.SUCCESS(
                f"Eventi elaborati: {len(events)}; completati: {succeeded}; "
                f"da riprovare: {retrying}; falliti: {failed}."
            )
        )
