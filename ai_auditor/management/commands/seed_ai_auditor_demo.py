from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from clients.models import Client
from dailyclose.models import DailyClose
from inventory.models import Ingredient
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale, ImportedSaleItem, POSConnection
from stores.models import Store


class Command(BaseCommand):
    help = "Add a realistic operational dataset for the Vendora AI Restaurant Auditor flow."

    def handle(self, *args, **options):
        User = get_user_model()
        client, _ = Client.objects.update_or_create(
            email="owner@vendora-ops.local",
            defaults={
                "name": "Vendora Restaurant Group",
                "owner_name": "Operations Owner",
                "phone": "555-0100",
                "status": Client.ACTIVE,
            },
        )
        owner, _ = User.objects.update_or_create(
            username="ops_owner",
            defaults={
                "email": "owner@vendora-ops.local",
                "role": User.CLIENT_OWNER,
                "client": client,
                "can_manage_inventory": True,
                "can_manage_paidouts": True,
                "can_close_day": True,
                "can_view_reports": True,
                "can_manage_pos": True,
            },
        )
        owner.set_password("ops12345")
        owner.save()

        downtown, _ = Store.objects.update_or_create(
            client=client,
            code="DWT",
            defaults={"name": "Downtown Grill", "address": "100 Main St"},
        )
        riverside, _ = Store.objects.update_or_create(
            client=client,
            code="RVR",
            defaults={"name": "Riverside Tacos", "address": "44 River Ave"},
        )
        manager, _ = User.objects.update_or_create(
            username="manager_sam",
            defaults={
                "email": "sam@vendora-ops.local",
                "first_name": "Sam",
                "last_name": "Patel",
                "role": User.MANAGER,
                "client": client,
                "store": downtown,
                "can_manage_inventory": True,
                "can_manage_paidouts": True,
                "can_close_day": True,
                "can_view_reports": True,
            },
        )
        manager.set_password("ops12345")
        manager.save()
        second_manager, _ = User.objects.update_or_create(
            username="manager_lee",
            defaults={
                "email": "lee@vendora-ops.local",
                "first_name": "Jordan",
                "last_name": "Lee",
                "role": User.MANAGER,
                "client": client,
                "store": riverside,
                "can_manage_inventory": True,
                "can_manage_paidouts": True,
                "can_close_day": True,
                "can_view_reports": True,
            },
        )
        second_manager.set_password("ops12345")
        second_manager.save()

        self._seed_inventory(client, downtown)
        self._seed_sales_and_closes(client, downtown, riverside, owner)
        self._seed_paidouts(downtown, riverside, manager, second_manager)
        self.stdout.write(self.style.SUCCESS("Vendora AI auditor operational dataset is ready. Login: ops_owner / ops12345"))

    def _seed_inventory(self, client, store):
        rows = [
            ("Chicken breast", "Protein", 22, "lb", 35, 3.20),
            ("Chicken thighs", "Protein", 18, "lb", 28, 2.45),
            ("Ground beef", "Protein", 44, "lb", 25, 4.80),
            ("Fryer oil", "Kitchen", 5, "gal", 12, 18.00),
            ("Canola oil backup", "Kitchen", 4, "gal", 8, 16.50),
            ("Rice", "Dry goods", 120, "lb", 40, 0.85),
            ("Black beans", "Dry goods", 75, "lb", 30, 1.05),
            ("Flour tortillas", "Dry goods", 210, "pcs", 150, 0.12),
            ("Burger buns", "Bakery", 84, "pcs", 60, 0.34),
            ("Lettuce", "Produce", 16, "heads", 18, 1.90),
            ("Tomatoes", "Produce", 24, "lb", 20, 1.60),
            ("Onions", "Produce", 55, "lb", 25, 0.72),
            ("Cilantro", "Produce", 8, "bunch", 10, 0.95),
            ("Avocado", "Produce", 42, "pcs", 30, 1.15),
            ("Salsa roja", "Prep", 18, "qt", 14, 3.10),
            ("Queso", "Dairy", 11, "qt", 12, 4.40),
            ("Cheddar", "Dairy", 28, "lb", 18, 3.90),
            ("To-go boxes", "Packaging", 180, "pcs", 120, 0.18),
            ("Napkins", "Packaging", 320, "pcs", 200, 0.03),
            ("Sanitizer", "Cleaning", 3, "gal", 5, 9.25),
        ]
        for name, category, qty, unit, reorder, cost in rows:
            Ingredient.objects.update_or_create(
                client=client,
                store=store,
                name=name,
                defaults={
                    "category": category,
                    "inventory_unit": unit,
                    "purchase_unit": unit,
                    "recipe_unit": unit,
                    "current_quantity": Decimal(str(qty)),
                    "low_stock_level": Decimal(str(reorder)),
                    "cost_per_unit": Decimal(str(cost)),
                    "average_cost": Decimal(str(cost)),
                    "is_active": True,
                },
            )

    def _seed_sales_and_closes(self, client, downtown, riverside, owner):
        today = timezone.localdate()
        for store in (downtown, riverside):
            connection, _ = POSConnection.objects.update_or_create(
                client=client,
                store=store,
                provider="toast",
                external_merchant_id=f"ops-{store.code.lower()}",
                defaults={"connection_name": f"{store.name} POS", "sync_status": "success", "is_active": True},
            )
            for offset in range(7):
                business_date = today - timedelta(days=offset)
                base = Decimal("4280.00") - Decimal(offset * 170)
                if store == riverside:
                    base -= Decimal("620.00")
                sale, _ = ImportedSale.objects.update_or_create(
                    connection=connection,
                    external_order_id=f"AI-DEMO-{store.code}-{business_date:%Y%m%d}",
                    defaults={
                        "business_date": business_date,
                        "total_amount": base,
                        "cash_amount": (base * Decimal("0.38")).quantize(Decimal("0.01")),
                        "card_amount": (base * Decimal("0.62")).quantize(Decimal("0.01")),
                        "tax_amount": (base * Decimal("0.08")).quantize(Decimal("0.01")),
                        "tip_amount": Decimal("0.00"),
                        "discount_amount": Decimal("25.00") if offset == 1 else Decimal("0.00"),
                        "status": "imported",
                        "processed_inventory": offset % 2 == 0,
                    },
                )
                ImportedSaleItem.objects.update_or_create(
                    sale=sale,
                    item_name="Chicken plate",
                    defaults={"external_item_id": "chicken-plate", "quantity": Decimal("86") - offset, "unit_price": Decimal("15.50")},
                )
                ImportedSaleItem.objects.update_or_create(
                    sale=sale,
                    item_name="Taco combo",
                    defaults={"external_item_id": "taco-combo", "quantity": Decimal("112") - offset, "unit_price": Decimal("12.25")},
                )
                DailyClose.objects.get_or_create(
                    store=store,
                    business_date=business_date,
                    defaults={
                        "opening_cash": Decimal("500.00"),
                        "cash_sales": (base * Decimal("0.38")).quantize(Decimal("0.01")),
                        "card_sales": (base * Decimal("0.62")).quantize(Decimal("0.01")),
                        "cash_paidouts": Decimal("140.00") if store == downtown else Decimal("310.00"),
                        "counted_cash": Decimal("1880.00") if store == downtown else Decimal("1475.00"),
                        "notes": "AI auditor operational close",
                        "closed_by": owner,
                        "created_by": owner,
                    },
                )

    def _seed_paidouts(self, downtown, riverside, manager, second_manager):
        today = timezone.localdate()
        rows = [
            (downtown, 1, "620.00", "other", "cash adjustment - register discrepancy", "cash", manager, time(23, 18)),
            (downtown, 1, "185.00", "meat", "emergency chicken purchase", "cash", manager, time(19, 42)),
            (downtown, 1, "142.00", "other", "oil top-off from local supplier", "cash", manager, time(20, 5)),
            (downtown, 2, "210.00", "maintenance", "fryer repair deposit", "cash", manager, time(21, 12)),
            (downtown, 3, "176.00", "groceries", "produce replacement", "cash", manager, time(18, 22)),
            (downtown, 4, "155.00", "other", "manager discretionary cash", "cash", manager, time(22, 5)),
            (downtown, 5, "88.00", "cleaning", "cleaning supplies", "card", manager, time(14, 10)),
            (downtown, 6, "96.00", "gas", "delivery fuel", "card", manager, time(13, 15)),
            (downtown, 7, "124.00", "vegetables", "farmers market vegetables", "cash", manager, time(9, 25)),
            (downtown, 0, "77.00", "refund", "guest refund", "cash", manager, time(16, 45)),
            (riverside, 1, "130.00", "groceries", "tortilla restock", "cash", second_manager, time(12, 30)),
            (riverside, 1, "92.00", "cleaning", "mop heads and sanitizer", "card", second_manager, time(10, 15)),
            (riverside, 2, "112.00", "utilities", "internet bill", "bank", second_manager, time(11, 20)),
            (riverside, 3, "64.00", "vegetables", "cilantro and onions", "cash", second_manager, time(9, 5)),
            (riverside, 4, "81.00", "other", "smallwares", "card", second_manager, time(15, 40)),
        ]
        while len(rows) < 30:
            idx = len(rows)
            store = downtown if idx % 2 == 0 else riverside
            user = manager if store == downtown else second_manager
            rows.append((store, (idx % 7) + 1, str(45 + idx * 3), "groceries", f"routine operating paidout {idx}", "cash" if idx % 3 == 0 else "card", user, time(12 + (idx % 8), 0)))

        for index, (store, offset, amount, category, description, source, user, paid_time) in enumerate(rows):
            business_date = today - timedelta(days=offset)
            paidout, created = PaidOut.objects.get_or_create(
                store=store,
                business_date=business_date,
                receipt_number=f"AI-DEMO-PO-{index:03d}",
                defaults={
                    "amount": Decimal(amount),
                    "category": category,
                    "description": description,
                    "vendor_payee": "Operations Vendor",
                    "payment_source": source,
                    "created_by": user,
                },
            )
            if created:
                timestamp = timezone.make_aware(datetime.combine(business_date, paid_time))
                PaidOut.objects.filter(pk=paidout.pk).update(created_at=timestamp)
