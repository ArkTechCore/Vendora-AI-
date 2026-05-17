from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from clients.models import Client
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale, POSConnection
from stores.models import Store


class Command(BaseCommand):
    help = "Add additional high-risk Spicy Grill sales transactions and suspicious paidouts."

    def handle(self, *args, **options):
        User = get_user_model()
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        client = Client.objects.get(name="Spicy Grill")
        store = Store.objects.get(client=client, code="SG-MAIN")
        owner = User.objects.get(username="john brick")
        manager = User.objects.get(username="spicy_manager")

        connection, _ = POSConnection.objects.get_or_create(
            client=client,
            store=store,
            provider="toast",
            external_merchant_id="sg-merchant-001",
            defaults={
                "connection_name": "Spicy Grill Toast POS",
                "environment": "production",
                "external_location_id": "sg-main-001",
                "is_active": True,
                "auto_sync_enabled": True,
                "sync_status": "success",
                "last_sync_at": timezone.now(),
            },
        )

        sales_created = self._add_sales(connection, today, yesterday)
        paidouts_created = self._add_paidouts(store, owner, manager, today, yesterday)

        yesterday_sales_count = ImportedSale.objects.filter(connection=connection, business_date=yesterday).count()
        yesterday_paidout_count = PaidOut.objects.filter(store=store, business_date=yesterday).count()

        self.stdout.write(self.style.SUCCESS("Spicy Grill risk data boosted."))
        self.stdout.write(f"New sales transactions created: {sales_created}")
        self.stdout.write(f"New suspicious paidouts created: {paidouts_created}")
        self.stdout.write(f"Yesterday sales records: {yesterday_sales_count}")
        self.stdout.write(f"Yesterday paidouts: {yesterday_paidout_count}")

    def _add_sales(self, connection, today, yesterday):
        sales_created = 0
        for day, label, base in [
            (yesterday, "Y", Decimal("185.00")),
            (today, "T", Decimal("142.00")),
        ]:
            for index in range(1, 31):
                total = (base + Decimal(index * 17)).quantize(Decimal("0.01"))
                cash = (total * Decimal("0.42")).quantize(Decimal("0.01"))
                _, created = ImportedSale.objects.update_or_create(
                    connection=connection,
                    external_order_id=f"SG-HEAVY-{label}-{index:03d}",
                    defaults={
                        "business_date": day,
                        "total_amount": total,
                        "cash_amount": cash,
                        "card_amount": (total - cash).quantize(Decimal("0.01")),
                        "tax_amount": (total * Decimal("0.066")).quantize(Decimal("0.01")),
                        "tip_amount": (total * Decimal("0.055")).quantize(Decimal("0.01")),
                        "discount_amount": Decimal("0.00"),
                        "status": "imported",
                    },
                )
                if created:
                    sales_created += 1
        return sales_created

    def _add_paidouts(self, store, owner, manager, today, yesterday):
        rows = [
            (yesterday, "cash", "other", "2750.00", "late night cash adjustment with missing receipt", "Register cash", manager),
            (yesterday, "cash", "other", "1995.00", "second cash adjustment after close", "Register cash", manager),
            (yesterday, "cash", "meat", "1685.40", "urgent chicken and lamb purchase no invoice", "Hudson Meat Supply", manager),
            (yesterday, "cash", "emergency_purchase", "1220.75", "emergency fryer oil restock cash paid", "Quick Market Wholesale", manager),
            (yesterday, "card", "maintenance", "940.30", "cooler repair rush fee", "Rapid Refrigeration", owner),
            (today - timedelta(days=2), "cash", "other", "1510.00", "cash shortage correction entered by same manager", "Register cash", manager),
            (today - timedelta(days=3), "cash", "other", "1340.00", "manager cash adjustment repeated pattern", "Register cash", manager),
            (today - timedelta(days=4), "cash", "meat", "1125.90", "same-day protein restock due to stock variance", "Hudson Meat Supply", manager),
            (today - timedelta(days=5), "cash", "emergency_purchase", "875.25", "oil and produce emergency purchase", "Restaurant Depot", manager),
            (today - timedelta(days=6), "cash", "other", "990.00", "cash paid vendor with incomplete receipt", "Unknown Vendor", manager),
        ]

        paidouts_created = 0
        for index, (day, source, category, amount, description, vendor, user) in enumerate(rows, start=1):
            _, created = PaidOut.objects.get_or_create(
                store=store,
                receipt_number=f"SG-SUSPICIOUS-{day:%Y%m%d}-{index:02d}",
                defaults={
                    "business_date": day,
                    "amount": Decimal(amount),
                    "category": category,
                    "description": description,
                    "vendor_payee": vendor,
                    "payment_source": source,
                    "created_by": user,
                    "approved": True,
                    "locked": True,
                },
            )
            if created:
                paidouts_created += 1
        return paidouts_created
