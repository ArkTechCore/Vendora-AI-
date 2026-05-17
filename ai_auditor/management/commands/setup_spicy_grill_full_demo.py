from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Set up the full Spicy Grill live demo dataset and platform super admin."

    def handle(self, *args, **options):
        call_command("ensure_super_admin")
        call_command("seed_spicy_grill_live")
        call_command("boost_spicy_grill_risk")
        self.stdout.write(self.style.SUCCESS("Full Spicy Grill demo setup is complete."))
        self.stdout.write("Super admin: mohammed / Mohammed@1339")
        self.stdout.write("Client login: john brick / John@1339")
