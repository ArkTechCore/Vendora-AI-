from datetime import timedelta
from decimal import Decimal
import random

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from clients.models import Client
from dailyclose.models import DailyClose
from inventory.models import Ingredient, InventoryCount, InventoryCountItem, MenuItem, PurchaseReceive, PurchaseReceiveItem, StockMovement, Vendor
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale, ImportedSaleItem, POSConnection
from pos_integrations.services import process_sale_inventory
from stores.models import Store


SEED_PREFIX = "QSLOAD"
random.seed(1339)


@transaction.atomic
def cleanup(store, client):
    ImportedSaleItem.objects.filter(sale__external_order_id__startswith=SEED_PREFIX).delete()
    ImportedSale.objects.filter(connection__client=client, external_order_id__startswith=SEED_PREFIX).delete()
    PurchaseReceiveItem.objects.filter(purchase__invoice_number__startswith=SEED_PREFIX).delete()
    PurchaseReceive.objects.filter(store=store, invoice_number__startswith=SEED_PREFIX).delete()
    PaidOut.objects.filter(store=store, vendor_payee__startswith=SEED_PREFIX).delete()
    InventoryCountItem.objects.filter(count__store=store, count__notes__startswith=SEED_PREFIX).delete()
    InventoryCount.objects.filter(store=store, notes__startswith=SEED_PREFIX).delete()
    DailyClose.objects.filter(store=store, notes__startswith=SEED_PREFIX).delete()
    StockMovement.objects.filter(ingredient__client=client, note__startswith=SEED_PREFIX).delete()
    StockMovement.objects.filter(ingredient__client=client, source_sale_id__startswith=SEED_PREFIX).delete()


def get_quickstop():
    client = Client.objects.get(name__iexact="Quick stop")
    store = Store.objects.filter(client=client, is_active=True).first()
    owner = User.objects.filter(client=client, role=User.CLIENT_OWNER).first() or User.objects.filter(is_superuser=True).first()
    if not store or not owner:
        raise RuntimeError("Quick stop needs an active store and owner/superuser before loading test data.")
    return client, store, owner


def ensure_catalog(client, store, owner):
    vendors = {}
    for name in ["QSLOAD Restaurant Depot", "QSLOAD Local Produce", "QSLOAD Packaging", "QSLOAD Dairy"]:
        vendors[name], _ = Vendor.objects.update_or_create(
            client=client,
            name=name,
            defaults={"contact_name": "Load Test", "phone": "555-0100", "is_active": True},
        )

    ingredient_rows = [
        ("Rice", "Dry Goods", "lb", "bag", 5000, 600, "0.82", vendors["QSLOAD Restaurant Depot"]),
        ("Chicken", "Meat", "lb", "case", 3200, 450, "2.35", vendors["QSLOAD Restaurant Depot"]),
        ("Mutton", "Meat", "lb", "case", 1600, 220, "5.60", vendors["QSLOAD Restaurant Depot"]),
        ("Oil", "Oil", "gal", "jug", 650, 90, "7.10", vendors["QSLOAD Restaurant Depot"]),
        ("Onion", "Produce", "lb", "bag", 2200, 260, "0.62", vendors["QSLOAD Local Produce"]),
        ("Tomato", "Produce", "lb", "box", 1800, 220, "0.78", vendors["QSLOAD Local Produce"]),
        ("Yogurt", "Dairy", "lb", "tub", 900, 120, "1.30", vendors["QSLOAD Dairy"]),
        ("Cream", "Dairy", "qt", "case", 720, 90, "2.20", vendors["QSLOAD Dairy"]),
        ("Spice Mix", "Spices", "oz", "bag", 5200, 700, "0.16", vendors["QSLOAD Restaurant Depot"]),
        ("Containers", "Packaging", "piece", "case", 16000, 2500, "0.11", vendors["QSLOAD Packaging"]),
        ("Cutlery Packs", "Packaging", "piece", "case", 18000, 3000, "0.03", vendors["QSLOAD Packaging"]),
    ]
    ingredients = {}
    for name, category, unit, purchase_unit, qty, low, cost, vendor in ingredient_rows:
        ingredient, _ = Ingredient.objects.update_or_create(
            client=client,
            store=store,
            name=name,
            defaults={
                "category": category,
                "vendor": vendor,
                "inventory_unit": unit,
                "recipe_unit": unit,
                "purchase_unit": purchase_unit,
                "purchase_to_inventory_factor": Decimal("1"),
                "inventory_to_recipe_factor": Decimal("1"),
                "low_stock_level": Decimal(low),
                "cost_per_unit": Decimal(cost),
                "average_cost": Decimal(cost),
                "last_cost": Decimal(cost),
                "is_active": True,
            },
        )
        Ingredient.objects.filter(pk=ingredient.pk).update(current_quantity=Decimal(qty))
        ingredient.refresh_from_db()
        StockMovement.objects.create(
            ingredient=ingredient,
            movement_type=StockMovement.ADJUSTMENT,
            quantity=Decimal(qty),
            note=f"{SEED_PREFIX} opening load quantity",
            created_by=owner,
        )
        ingredients[name] = ingredient

    menu_rows = [
        ("QSLOAD Chicken Biryani", "12.99", [("Rice", ".35"), ("Chicken", ".30"), ("Oil", ".03"), ("Onion", ".08"), ("Yogurt", ".05"), ("Spice Mix", ".40"), ("Containers", "1"), ("Cutlery Packs", "1")]),
        ("QSLOAD Mutton Biryani", "15.99", [("Rice", ".35"), ("Mutton", ".34"), ("Oil", ".03"), ("Onion", ".08"), ("Yogurt", ".05"), ("Spice Mix", ".45"), ("Containers", "1"), ("Cutlery Packs", "1")]),
        ("QSLOAD Butter Chicken", "13.99", [("Chicken", ".35"), ("Oil", ".02"), ("Onion", ".06"), ("Tomato", ".10"), ("Cream", ".20"), ("Spice Mix", ".35"), ("Containers", "1"), ("Cutlery Packs", "1")]),
        ("QSLOAD Curry Bowl", "9.99", [("Rice", ".28"), ("Chicken", ".18"), ("Oil", ".02"), ("Tomato", ".12"), ("Spice Mix", ".30"), ("Containers", "1"), ("Cutlery Packs", "1")]),
        ("QSLOAD Family Tray", "49.99", [("Rice", "2.2"), ("Chicken", "1.8"), ("Oil", ".15"), ("Onion", ".40"), ("Yogurt", ".25"), ("Spice Mix", "2.0"), ("Containers", "1"), ("Cutlery Packs", "6")]),
    ]
    menu_items = []
    for name, price, recipe_rows in menu_rows:
        item, _ = MenuItem.objects.update_or_create(
            client=client,
            store=store,
            name=name,
            defaults={"category": "Load Test", "selling_price": Decimal(price), "external_pos_name": name, "external_pos_id": name, "is_active": True},
        )
        item.recipe_items.all().delete()
        for ingredient_name, quantity in recipe_rows:
            item.recipe_items.create(ingredient=ingredients[ingredient_name], quantity_used=Decimal(quantity), recipe_unit=ingredients[ingredient_name].recipe_unit)
        menu_items.append(item)
    return vendors, ingredients, menu_items


def load_data(days=45, orders_per_day=12):
    client, store, owner = get_quickstop()
    cleanup(store, client)
    vendors, ingredients, menu_items = ensure_catalog(client, store, owner)
    pos, _ = POSConnection.objects.update_or_create(
        client=client,
        store=store,
        provider="csv",
        defaults={"connection_name": "QSLOAD POS Import", "is_active": True, "auto_sync_enabled": True, "sync_status": "success"},
    )

    today = timezone.localdate()
    sales_created = 0
    sale_items_created = 0
    paidouts_created = 0
    purchases_created = 0
    counts_created = 0
    closes_created = 0

    for day_index in range(days):
        business_date = today - timedelta(days=days - day_index - 1)
        daily_cash = Decimal("0.00")
        daily_card = Decimal("0.00")

        if day_index % 6 == 0:
            purchase = PurchaseReceive.objects.create(
                store=store,
                vendor=vendors["QSLOAD Restaurant Depot"],
                invoice_number=f"{SEED_PREFIX}-INV-{day_index:03d}",
                invoice_date=business_date,
                status=PurchaseReceive.POSTED,
                subtotal=Decimal("0.00"),
                total=Decimal("0.00"),
                received_by=owner,
                notes=f"{SEED_PREFIX} recurring inventory receive",
            )
            total = Decimal("0.00")
            for ingredient in random.sample(list(ingredients.values()), 5):
                qty = Decimal(random.randint(24, 160))
                unit_cost = ingredient.average_cost
                line_total = (qty * unit_cost).quantize(Decimal("0.01"))
                PurchaseReceiveItem.objects.create(
                    purchase=purchase,
                    ingredient=ingredient,
                    purchase_quantity=qty,
                    purchase_unit=ingredient.purchase_unit,
                    quantity_received=qty,
                    inventory_unit=ingredient.inventory_unit,
                    unit_cost=unit_cost,
                    total_cost=line_total,
                )
                total += line_total
            purchase.subtotal = total
            purchase.total = total
            purchase.save(update_fields=["subtotal", "total"])
            purchases_created += 1

        for order_num in range(orders_per_day):
            chosen = random.choices(menu_items, weights=[38, 18, 24, 28, 7], k=random.randint(1, 3))
            sale = ImportedSale.objects.create(
                connection=pos,
                external_order_id=f"{SEED_PREFIX}-{business_date:%Y%m%d}-{order_num:03d}",
                business_date=business_date,
                total_amount=Decimal("0.00"),
                cash_amount=Decimal("0.00"),
                card_amount=Decimal("0.00"),
                status="imported",
            )
            total = Decimal("0.00")
            for item in chosen:
                qty = Decimal(random.choice([1, 1, 1, 2, 3]))
                line_total = item.selling_price * qty
                ImportedSaleItem.objects.create(
                    sale=sale,
                    external_item_id=item.external_pos_id,
                    item_name=item.name,
                    quantity=qty,
                    unit_price=item.selling_price,
                    mapped_menu_item=item,
                )
                total += line_total
                sale_items_created += 1
            cash = total if random.random() < 0.38 else Decimal("0.00")
            card = total - cash
            sale.total_amount = total
            sale.cash_amount = cash
            sale.card_amount = card
            sale.save(update_fields=["total_amount", "cash_amount", "card_amount"])
            process_sale_inventory(sale, owner)
            daily_cash += cash
            daily_card += card
            sales_created += 1

        if day_index % 2 == 0:
            for paidout_num in range(random.randint(1, 3)):
                amount = Decimal(f"{25 + day_index}.{paidout_num + random.randint(10, 89)}").quantize(Decimal("0.01"))
                PaidOut.objects.create(
                    store=store,
                    business_date=business_date,
                    amount=amount,
                    category=random.choice(["groceries", "cleaning", "maintenance", "gas", "emergency_purchase"]),
                    description=f"{SEED_PREFIX} operating expense test",
                    vendor_payee=f"{SEED_PREFIX} Vendor {day_index:03d}-{paidout_num}",
                    payment_source=random.choice(["cash", "card", "bank"]),
                    receipt_number=f"{SEED_PREFIX}-PO-{day_index:03d}-{paidout_num}",
                    created_by=owner,
                )
                paidouts_created += 1

        if day_index % 7 == 0 or day_index == days - 1:
            count, _ = InventoryCount.objects.update_or_create(
                store=store,
                business_date=business_date,
                defaults={
                    "status": InventoryCount.CLOSED,
                    "counted_by": owner,
                    "notes": f"{SEED_PREFIX} weekly inventory control count",
                    "closed_at": timezone.now(),
                },
            )
            count.items.all().delete()
            for ingredient in ingredients.values():
                snapshot = max(Decimal("0"), ingredient.current_quantity + Decimal(random.randint(-8, 8)))
                InventoryCountItem.objects.create(count=count, ingredient=ingredient, counted_quantity=snapshot, unit_cost_snapshot=ingredient.average_cost)
            counts_created += 1

        if day_index >= days - 14:
            paidout_total = PaidOut.objects.filter(store=store, business_date=business_date, vendor_payee__startswith=SEED_PREFIX).values_list("amount", flat=True)
            cash_paidouts = sum(paidout_total, Decimal("0.00"))
            counted = Decimal("500.00") + daily_cash - cash_paidouts + Decimal(random.randint(-18, 18))
            close, created_close = DailyClose.objects.get_or_create(
                store=store,
                business_date=business_date,
                defaults={
                    "opening_cash": Decimal("500.00"),
                    "cash_sales": daily_cash,
                    "card_sales": daily_card,
                    "cash_paidouts": cash_paidouts,
                    "counted_cash": counted,
                    "notes": f"{SEED_PREFIX} daily close load test",
                    "closed_by": owner,
                    "created_by": owner,
                },
            )
            if created_close:
                closes_created += 1

    return {
        "client": client.name,
        "store": store.name,
        "days": days,
        "sales": sales_created,
        "sale_items": sale_items_created,
        "paidouts": paidouts_created,
        "purchases": purchases_created,
        "inventory_counts": counts_created,
        "daily_closes": closes_created,
        "stock_movements": StockMovement.objects.filter(ingredient__client=client, source_sale_id__startswith=SEED_PREFIX).count(),
    }


result = load_data()
print(result)
