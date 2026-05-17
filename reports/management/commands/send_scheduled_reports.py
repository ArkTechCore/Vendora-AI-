from django.core.management.base import BaseCommand

from clients.models import Client
from reports.notifications import period_dates, send_client_period_report, send_platform_period_report


class Command(BaseCommand):
    help = "Send weekly or month-end VendoraOps email summaries through the configured email backend."

    def add_arguments(self, parser):
        parser.add_argument("--period", choices=["weekly", "monthly"], required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        start_date, end_date, label = period_dates(options["period"])
        clients = Client.objects.filter(status=Client.ACTIVE).order_by("name")
        self.stdout.write(f"{label} report window: {start_date} to {end_date}")
        if options["dry_run"]:
            self.stdout.write(f"Would email {clients.count()} active client report(s) and one platform-safe super admin report.")
            return
        sent = 0
        for client in clients:
            sent += send_client_period_report(client, start_date, end_date, label)
        sent += send_platform_period_report(start_date, end_date, label)
        self.stdout.write(self.style.SUCCESS(f"Email send attempts completed. Messages accepted: {sent}"))
