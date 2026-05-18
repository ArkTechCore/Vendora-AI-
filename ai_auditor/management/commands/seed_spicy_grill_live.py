from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from clients.models import Client
from dailyclose.models import DailyClose
from inventory.models import Ingredient, PurchaseReceive, PurchaseReceiveItem, StockMovement, Vendor
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale, ImportedSaleItem, POSConnection
from stores.models import Store


class Command(BaseCommand):
    help = "Seed Spicy Grill with production-style sales, paidouts, inventory, and audit-ready records."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="john brick")
        parser.add_argument("--password", default="John@1339")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

        User = get_user_model()
        client, _ = Client.objects.update_or_create(
            name="Spicy Grill",
            defaults={
                "owner_name": "John Brick",
                "email": "john.brick@spicygrill.local",
                "phone": "555-0139",
                "street_address": "1400 Market Street",
                "city": "Jersey City",
                "state": "NJ",
                "postal_code": "07302",
                "country": "US",
                "status": Client.ACTIVE,
            },
        )
        owner, _ = User.objects.get_or_create(username=username)
        owner.first_name = "John"
        owner.last_name = "Brick"
        owner.email = "john.brick@spicygrill.local"
        owner.role = User.CLIENT_OWNER
        owner.client = client
        owner.store = None
        owner.is_active = True
        owner.can_manage_inventory = True
        owner.can_manage_paidouts = True
        owner.can_close_day = True
        owner.can_view_reports = True
        owner.can_manage_pos = True
        owner.set_password(password)
        owner.save()

        store_configs = [
            ("SG-MAIN", "Spicy Grill Main", "1400 Market Street, Jersey City, NJ 07302", "spicy_manager", "Marco", "Diaz"),
            ("SG-WEST", "Spicy Grill West", "88 West Side Avenue, Jersey City, NJ 07305", "spicy_west_manager", "Nina", "Khan"),
        ]
        seeded_stores = []
        for code, name, address, manager_username, first_name, last_name in store_configs:
            store, _ = Store.objects.update_or_create(
                client=client,
                code=code,
                defaults={
                    "name": name,
                    "address": address,
                    "phone": "555-0139",
                    "is_active": True,
                },
            )
            manager = self._ensure_manager(User, client, store, manager_username, first_name, last_name)
            self._seed_inventory(client, store)
            self._seed_purchase_receives(client, store, owner)
            self._seed_inventory_movements(client, store, manager)
            connection = self._seed_sales(client, store)
            self._seed_paidouts(store, owner, manager)
            self._seed_daily_closes(store, owner, connection)
            seeded_stores.append(store)

        self.stdout.write(self.style.SUCCESS("Spicy Grill live dataset is ready."))
        self.stdout.write(f"Login: {username} / {password}")
        self.stdout.write("Stores: " + ", ".join(f"{store.name} ({store.code})" for store in seeded_stores))

    def _ensure_manager(self, User, client, store, username, first_name, last_name):
        manager, _ = User.objects.get_or_create(username=username)
        manager.first_name = first_name
        manager.last_name = last_name
        manager.email = f"{username.replace('_', '.')}@spicygrill.local"
        manager.role = User.MANAGER
        manager.client = client
        manager.store = store
        manager.can_manage_inventory = True
        manager.can_manage_paidouts = True
        manager.can_close_day = True
        manager.can_view_reports = True
        manager.is_active = True
        manager.set_password("Manager@1339")
        manager.save()
        return manager

    def _seed_inventory(self, client, store):
        rows = [
            ("Chicken breast", "Protein", "lb", "18.000", "45.000", "3.35"),
            ("Chicken thighs", "Protein", "lb", "22.000", "38.000", "2.55"),
            ("Lamb cubes", "Protein", "lb", "12.000", "28.000", "6.75"),
            ("Ground beef", "Protein", "lb", "36.000", "34.000", "4.95"),
            ("Fryer oil", "Kitchen", "gal", "4.000", "14.000", "18.90"),
            ("Canola oil backup", "Kitchen", "gal", "3.000", "8.000", "16.75"),
            ("Basmati rice", "Dry goods", "lb", "95.000", "70.000", "1.10"),
            ("Flour tortillas", "Dry goods", "pcs", "160.000", "220.000", "0.16"),
            ("Burger buns", "Bakery", "pcs", "72.000", "95.000", "0.38"),
            ("Lettuce", "Produce", "heads", "10.000", "22.000", "1.95"),
            ("Tomatoes", "Produce", "lb", "18.000", "35.000", "1.70"),
            ("Onions", "Produce", "lb", "42.000", "38.000", "0.76"),
            ("Cilantro", "Produce", "bunch", "6.000", "12.000", "0.98"),
            ("Jalapenos", "Produce", "lb", "7.000", "10.000", "1.25"),
            ("Avocado", "Produce", "pcs", "28.000", "45.000", "1.20"),
            ("Salsa roja", "Prep", "qt", "9.000", "18.000", "3.20"),
            ("Queso", "Dairy", "qt", "8.000", "14.000", "4.65"),
            ("Cheddar", "Dairy", "lb", "20.000", "24.000", "4.05"),
            ("To-go boxes", "Packaging", "pcs", "130.000", "180.000", "0.20"),
            ("Napkins", "Packaging", "pcs", "260.000", "240.000", "0.03"),
            ("Sanitizer", "Cleaning", "gal", "2.000", "6.000", "9.50"),
        ]
        for name, category, unit, current, reorder, cost in rows:
            Ingredient.objects.update_or_create(
                client=client,
                store=store,
                name=name,
                defaults={
                    "category": category,
                    "inventory_unit": unit,
                    "purchase_unit": unit,
                    "recipe_unit": unit,
                    "current_quantity": Decimal(current),
                    "low_stock_level": Decimal(reorder),
                    "cost_per_unit": Decimal(cost),
                    "average_cost": Decimal(cost),
                    "last_cost": Decimal(cost),
                    "is_active": True,
                },
            )

    def _seed_purchase_receives(self, client, store, owner):
        vendors = {}
        for name, contact, phone in [
            ("Hudson Meat Supply", "Anthony Russo", "555-0191"),
            ("Fresh Valley Produce", "Mina Shah", "555-0192"),
            ("Quick Market Wholesale", "Operations Desk", "555-0193"),
            ("Restaurant Depot", "Receiving Desk", "555-0194"),
        ]:
            vendor, _ = Vendor.objects.update_or_create(
                client=client,
                name=name,
                defaults={
                    "contact_name": contact,
                    "phone": phone,
                    "email": f"{name.lower().replace(' ', '.')}@vendor.local",
                    "address": "Vendor route account",
                    "is_active": True,
                },
            )
            vendors[name] = vendor

        today = timezone.localdate()
        purchases = [
            {
                "invoice": "SG-INV-MEAT-001",
                "vendor": vendors["Hudson Meat Supply"],
                "date": today - timedelta(days=1),
                "items": [
                    ("Chicken breast", "40.000", "3.45"),
                    ("Chicken thighs", "35.000", "2.65"),
                    ("Lamb cubes", "28.000", "6.95"),
                    ("Ground beef", "32.000", "5.10"),
                ],
            },
            {
                "invoice": "SG-INV-PROD-001",
                "vendor": vendors["Fresh Valley Produce"],
                "date": today - timedelta(days=1),
                "items": [
                    ("Lettuce", "18.000", "2.05"),
                    ("Tomatoes", "34.000", "1.82"),
                    ("Onions", "45.000", "0.82"),
                    ("Cilantro", "14.000", "1.05"),
                    ("Avocado", "50.000", "1.28"),
                ],
            },
            {
                "invoice": "SG-INV-OIL-001",
                "vendor": vendors["Quick Market Wholesale"],
                "date": today - timedelta(days=2),
                "items": [
                    ("Fryer oil", "18.000", "19.25"),
                    ("Canola oil backup", "10.000", "17.10"),
                    ("To-go boxes", "280.000", "0.22"),
                    ("Napkins", "500.000", "0.04"),
                    ("Sanitizer", "8.000", "9.85"),
                ],
            },
            {
                "invoice": "SG-INV-DRY-001",
                "vendor": vendors["Restaurant Depot"],
                "date": today - timedelta(days=3),
                "items": [
                    ("Basmati rice", "120.000", "1.18"),
                    ("Flour tortillas", "320.000", "0.18"),
                    ("Burger buns", "140.000", "0.42"),
                    ("Salsa roja", "20.000", "3.35"),
                    ("Queso", "18.000", "4.80"),
                    ("Cheddar", "35.000", "4.20"),
                ],
            },
        ]

        for purchase_data in purchases:
            subtotal = Decimal("0.00")
            for ingredient_name, quantity, unit_cost in purchase_data["items"]:
                subtotal += Decimal(quantity) * Decimal(unit_cost)
            subtotal = subtotal.quantize(Decimal("0.01"))
            tax_fees = (subtotal * Decimal("0.035")).quantize(Decimal("0.01"))
            purchase, created = PurchaseReceive.objects.get_or_create(
                store=store,
                invoice_number=purchase_data["invoice"],
                defaults={
                    "vendor": purchase_data["vendor"],
                    "invoice_date": purchase_data["date"],
                    "due_date": purchase_data["date"] + timedelta(days=14),
                    "status": PurchaseReceive.POSTED,
                    "subtotal": subtotal,
                    "tax_fees": tax_fees,
                    "total": subtotal + tax_fees,
                    "posted_at": timezone.now(),
                    "received_by": owner,
                    "notes": "Seeded Spicy Grill purchase receive for inventory audit context.",
                },
            )
            if not created:
                continue
            for ingredient_name, quantity, unit_cost in purchase_data["items"]:
                ingredient = Ingredient.objects.get(client=client, store=store, name=ingredient_name)
                PurchaseReceiveItem.objects.create(
                    purchase=purchase,
                    ingredient=ingredient,
                    vendor_item_name=ingredient_name,
                    pack_size=ingredient.inventory_unit,
                    purchase_quantity=Decimal(quantity),
                    purchase_unit=ingredient.purchase_unit,
                    quantity_received=Decimal(quantity),
                    inventory_unit=ingredient.inventory_unit,
                    unit_cost=Decimal(unit_cost),
                )

    def _seed_inventory_movements(self, client, store, manager):
        rows = [
            ("Chicken breast", StockMovement.WASTE, "18.000", "Prep waste after over-portioning review"),
            ("Chicken thighs", StockMovement.USAGE, "24.000", "High usage from mixed grill sales"),
            ("Lamb cubes", StockMovement.WASTE, "6.000", "Trim loss above expected yield"),
            ("Fryer oil", StockMovement.USAGE, "9.000", "Unusually high fryer oil drawdown"),
            ("Tomatoes", StockMovement.WASTE, "12.000", "Spoilage from over-prep"),
            ("Lettuce", StockMovement.WASTE, "8.000", "Damaged heads discarded before service"),
            ("Salsa roja", StockMovement.USAGE, "7.000", "High sauce usage during dinner rush"),
            ("To-go boxes", StockMovement.USAGE, "95.000", "Packaging use from delivery spike"),
        ]
        for ingredient_name, movement_type, quantity, note in rows:
            ingredient = Ingredient.objects.get(client=client, store=store, name=ingredient_name)
            if StockMovement.objects.filter(ingredient=ingredient, movement_type=movement_type, note=note).exists():
                continue
            StockMovement.objects.create(
                ingredient=ingredient,
                movement_type=movement_type,
                quantity=Decimal(quantity),
                note=note,
                created_by=manager,
            )

    def _seed_sales(self, client, store):
        today = timezone.localdate()
        connection, _ = POSConnection.objects.update_or_create(
            client=client,
            store=store,
            provider="toast",
            external_merchant_id=f"sg-{store.code.lower()}",
            defaults={
                "connection_name": "Spicy Grill Toast POS",
                "environment": "production",
                "external_location_id": f"{store.code.lower()}-001",
                "is_active": True,
                "auto_sync_enabled": True,
                "sync_status": "success",
                "last_sync_at": timezone.now(),
            },
        )
        for day_offset in range(7, 0, -1):
            business_date = today - timedelta(days=day_offset)
            daily_base = Decimal("11200.00") + Decimal(day_offset * 475)
            for batch in range(1, 7):
                total = (daily_base / Decimal("6") + Decimal(batch * 31)).quantize(Decimal("0.01"))
                cash = (total * Decimal("0.34")).quantize(Decimal("0.01"))
                sale, _ = ImportedSale.objects.update_or_create(
                    connection=connection,
                    external_order_id=f"{store.code}-{business_date:%Y%m%d}-B{batch}",
                    defaults={
                        "business_date": business_date,
                        "total_amount": total,
                        "cash_amount": cash,
                        "card_amount": total - cash,
                        "tax_amount": (total * Decimal("0.066")).quantize(Decimal("0.01")),
                        "tip_amount": (total * Decimal("0.072")).quantize(Decimal("0.01")),
                        "discount_amount": Decimal("0.00"),
                        "status": "imported",
                    },
                )
                ImportedSaleItem.objects.update_or_create(
                    sale=sale,
                    external_item_id=f"spicy-combo-{batch}",
                    defaults={
                        "item_name": "Spicy mixed grill combo",
                        "quantity": Decimal("18") + batch,
                        "unit_price": Decimal("24.50"),
                    },
                )
        return connection

    def _seed_paidouts(self, store, owner, manager):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        rows = [
            (yesterday, "cash", "other", "1850.00", "late night cash adjustment - emergency drawer correction", "Register cash"),
            (yesterday, "cash", "meat", "1425.75", "urgent lamb and chicken purchase without invoice", "Hudson Meat Supply"),
            (yesterday, "cash", "emergency_purchase", "980.40", "emergency fryer oil and produce restock", "Quick Market Wholesale"),
            (yesterday, "card", "maintenance", "765.20", "walk-in cooler repair after close", "Rapid Refrigeration"),
            (today - timedelta(days=2), "cash", "other", "1320.00", "manager cash adjustment for vendor shortage", "Register cash"),
            (today - timedelta(days=2), "cash", "meat", "1188.35", "same-day chicken reorder due to stockout", "Hudson Meat Supply"),
            (today - timedelta(days=3), "cash", "emergency_purchase", "890.10", "fryer oil emergency buy", "Restaurant Depot"),
            (today - timedelta(days=3), "bank", "utilities", "1105.65", "gas utility catch-up payment", "Utility Provider"),
            (today - timedelta(days=4), "cash", "vegetables", "640.90", "produce restock after prep shortage", "Fresh Valley Produce"),
            (today - timedelta(days=5), "cash", "other", "1240.00", "cash adjustment with missing receipt", "Register cash"),
            (today - timedelta(days=6), "card", "cleaning", "520.50", "deep cleaning after hood inspection", "CleanPro Services"),
            (today - timedelta(days=7), "cash", "meat", "1044.25", "weekend protein rush purchase", "Hudson Meat Supply"),
        ]
        for index, (business_date, source, category, amount, description, vendor) in enumerate(rows, start=1):
            amount_value = Decimal(amount)
            existing = PaidOut.objects.filter(
                store=store,
                business_date=business_date,
                amount=amount_value,
                category=category,
                payment_source=source,
            ).first()
            if existing:
                continue
            PaidOut.objects.get_or_create(
                store=store,
                receipt_number=f"{store.code}-PO-{business_date:%Y%m%d}-{index:02d}",
                defaults={
                    "business_date": business_date,
                    "amount": amount_value,
                    "category": category,
                    "description": description,
                    "vendor_payee": vendor,
                    "payment_source": source,
                    "created_by": manager if index % 3 else owner,
                    "approved": True,
                    "locked": True,
                },
            )

    def _seed_daily_closes(self, store, owner, connection):
        for row in ImportedSale.objects.filter(connection=connection).values("business_date").distinct():
            business_date = row["business_date"]
            sales = ImportedSale.objects.filter(connection=connection, business_date=business_date)
            cash_sales = sum((sale.cash_amount for sale in sales), Decimal("0.00"))
            card_sales = sum((sale.card_amount for sale in sales), Decimal("0.00"))
            paidouts = PaidOut.objects.filter(store=store, business_date=business_date, payment_source="cash")
            cash_paidouts = sum((paidout.amount for paidout in paidouts), Decimal("0.00"))
            expected_cash = Decimal("750.00") + cash_sales - cash_paidouts
            counted_cash = expected_cash - Decimal("285.00") if cash_paidouts > Decimal("1000.00") else expected_cash - Decimal("42.00")
            DailyClose.objects.get_or_create(
                store=store,
                business_date=business_date,
                defaults={
                    "opening_cash": Decimal("750.00"),
                    "cash_sales": cash_sales.quantize(Decimal("0.01")),
                    "card_sales": card_sales.quantize(Decimal("0.01")),
                    "cash_paidouts": cash_paidouts.quantize(Decimal("0.01")),
                    "counted_cash": counted_cash.quantize(Decimal("0.01")),
                    "notes": "Operational close seeded for Spicy Grill audit review.",
                    "closed_by": owner,
                    "created_by": owner,
                },
            )
