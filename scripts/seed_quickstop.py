from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from accounts.models import User
from accounts.services import log_audit
from clients.models import Client
from dailyclose.models import DailyClose
from inventory.models import (
    Ingredient,
    InventoryCount,
    InventoryCountItem,
    MenuItem,
    PurchaseReceive,
    PurchaseReceiveItem,
    RecipeIngredient,
    StockMovement,
    Vendor,
)
from inventory.services import close_inventory_count, get_actual_vs_theoretical_rows
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale, ImportedSaleItem, POSConnection
from pos_integrations.services import process_sale_inventory
from stores.models import Store


client = Client.objects.get(name__iexact="Quick stop")
store = Store.objects.filter(client=client, is_active=True).first()
owner = User.objects.filter(client=client, role=User.CLIENT_OWNER).first() or User.objects.get(username="mohammed")
manager, _ = User.objects.get_or_create(
    username="quickstop_manager",
    defaults={
        "role": User.MANAGER,
        "client": client,
        "store": store,
        "email": "quickstop_manager@example.com",
        "first_name": "Quick stop",
        "last_name": "Manager",
    },
)
manager.role = User.MANAGER
manager.client = client
manager.store = store
manager.is_active = True
manager.set_password("Quickstop@1339")
manager.save()

today = timezone.localdate()
start_date = today - timedelta(days=1)


def cleanup_seed_transactions():
    ImportedSaleItem.objects.filter(sale__connection__client=client, sale__external_order_id="TEST-1001").delete()
    ImportedSale.objects.filter(connection__client=client, external_order_id="TEST-1001").delete()
    PurchaseReceiveItem.objects.filter(purchase__store=store, purchase__invoice_number="RD-1001").delete()
    PurchaseReceive.objects.filter(store=store, invoice_number="RD-1001").delete()
    PaidOut.objects.filter(store=store, amount=Decimal("35.00"), vendor_payee="Local Grocery").delete()
    DailyClose.objects.filter(store=store, business_date=today).delete()
    InventoryCountItem.objects.filter(count__store=store, count__business_date__in=[start_date, today]).delete()
    InventoryCount.objects.filter(store=store, business_date__in=[start_date, today]).delete()
    StockMovement.objects.filter(ingredient__client=client, note__startswith="Starter inventory setup").delete()
    StockMovement.objects.filter(ingredient__client=client, source_sale_id="TEST-1001").delete()


cleanup_seed_transactions()

vendors_data = [
    ("Restaurant Depot", "Sales Desk", "000-000-0000", "Bulk dry goods, meat, oil"),
    ("Local Produce Supplier", "Produce Contact", "000-000-0000", "Vegetables, herbs"),
    ("Dairy Supplier", "Dairy Contact", "000-000-0000", "Milk, cream, yogurt"),
    ("Packaging Supplier", "Packaging Contact", "000-000-0000", "Containers, bags, cups"),
]
vendors = {}
for name, contact, phone, notes in vendors_data:
    vendor, _ = Vendor.objects.update_or_create(
        client=client,
        name=name,
        defaults={"contact_name": contact, "phone": phone, "address": notes, "is_active": True},
    )
    vendors[name] = vendor

ingredients_data = [
    ("Basmati Rice", "Dry Goods", "Restaurant Depot", "lb", "bag", "50", "100", "25", "0.85"),
    ("Chicken", "Meat", "Restaurant Depot", "lb", "case", "40", "80", "20", "2.45"),
    ("Mutton", "Meat", "Restaurant Depot", "lb", "case", "35", "40", "10", "5.75"),
    ("Cooking Oil", "Oil", "Restaurant Depot", "gal", "jug", "5", "10", "3", "7.20"),
    ("Onion", "Produce", "Local Produce Supplier", "lb", "bag", "25", "50", "15", "0.65"),
    ("Tomato", "Produce", "Local Produce Supplier", "lb", "box", "25", "40", "10", "0.80"),
    ("Yogurt", "Dairy", "Dairy Supplier", "lb", "tub", "10", "30", "8", "1.35"),
    ("Milk", "Dairy", "Dairy Supplier", "gal", "case", "4", "12", "4", "4.10"),
    ("Heavy Cream", "Dairy", "Dairy Supplier", "qt", "case", "12", "24", "6", "2.30"),
    ("Spices Mix", "Spices", "Restaurant Depot", "oz", "bag", "80", "160", "40", "0.18"),
    ("Lentils", "Dry Goods", "Restaurant Depot", "lb", "bag", "25", "50", "10", "1.10"),
    ("Sugar", "Dry Goods", "Restaurant Depot", "lb", "bag", "50", "50", "10", "0.72"),
    ("Ghee", "Oil", "Restaurant Depot", "lb", "tub", "10", "20", "5", "4.50"),
    ("To-Go Container", "Packaging", "Packaging Supplier", "piece", "case", "500", "500", "100", "0.12"),
    ("Spoon/Fork Pack", "Packaging", "Packaging Supplier", "piece", "case", "1000", "1000", "200", "0.03"),
]
ingredients = {}
starting_counts = {}
for name, category, vendor_name, inv_unit, purchase_unit, conversion, start_qty, low, cost in ingredients_data:
    ingredient, _ = Ingredient.objects.update_or_create(
        client=client,
        store=store,
        name=name,
        defaults={
            "category": category,
            "vendor": vendors[vendor_name],
            "inventory_unit": inv_unit,
            "recipe_unit": inv_unit,
            "purchase_unit": purchase_unit,
            "purchase_to_inventory_factor": Decimal(conversion),
            "inventory_to_recipe_factor": Decimal("1"),
            "low_stock_level": Decimal(low),
            "average_cost": Decimal(cost),
            "last_cost": Decimal(cost),
            "cost_per_unit": Decimal(cost),
            "is_active": True,
        },
    )
    Ingredient.objects.filter(pk=ingredient.pk).update(current_quantity=Decimal(start_qty))
    ingredient.refresh_from_db()
    ingredients[name] = ingredient
    starting_counts[name] = Decimal(start_qty)
    StockMovement.objects.create(
        ingredient=ingredient,
        movement_type=StockMovement.ADJUSTMENT,
        quantity=Decimal(start_qty),
        note="Starter inventory setup for Quick stop",
        created_by=owner,
    )

menu_data = [
    ("Chicken Biryani", "Rice Entree", "12.99", "Chicken Biryani"),
    ("Mutton Biryani", "Rice Entree", "15.99", "Mutton Biryani"),
    ("Butter Chicken", "Curry", "13.99", "Butter Chicken"),
    ("Dalcha", "Curry", "7.99", "Dalcha"),
    ("Kheer", "Dessert", "4.99", "Kheer"),
    ("Family Chicken Biryani Tray", "Catering", "49.99", "Family Chicken Biryani Tray"),
]
menu_items = {}
for name, category, price, pos_name in menu_data:
    item, _ = MenuItem.objects.update_or_create(
        client=client,
        store=store,
        name=name,
        defaults={
            "category": category,
            "selling_price": Decimal(price),
            "external_pos_name": pos_name,
            "external_pos_id": pos_name,
            "is_active": True,
        },
    )
    menu_items[name] = item

recipes = {
    "Chicken Biryani": [("Basmati Rice", "0.35", "lb"), ("Chicken", "0.30", "lb"), ("Cooking Oil", "0.03", "gal"), ("Onion", "0.08", "lb"), ("Yogurt", "0.05", "lb"), ("Spices Mix", "0.40", "oz"), ("To-Go Container", "1", "piece"), ("Spoon/Fork Pack", "1", "piece")],
    "Mutton Biryani": [("Basmati Rice", "0.35", "lb"), ("Mutton", "0.35", "lb"), ("Cooking Oil", "0.03", "gal"), ("Onion", "0.08", "lb"), ("Yogurt", "0.05", "lb"), ("Spices Mix", "0.45", "oz"), ("To-Go Container", "1", "piece"), ("Spoon/Fork Pack", "1", "piece")],
    "Butter Chicken": [("Chicken", "0.35", "lb"), ("Cooking Oil", "0.02", "gal"), ("Onion", "0.06", "lb"), ("Tomato", "0.10", "lb"), ("Heavy Cream", "0.20", "qt"), ("Spices Mix", "0.35", "oz"), ("Ghee", "0.05", "lb"), ("To-Go Container", "1", "piece"), ("Spoon/Fork Pack", "1", "piece")],
    "Dalcha": [("Lentils", "0.18", "lb"), ("Mutton", "0.08", "lb"), ("Cooking Oil", "0.015", "gal"), ("Onion", "0.05", "lb"), ("Tomato", "0.08", "lb"), ("Spices Mix", "0.30", "oz"), ("To-Go Container", "1", "piece"), ("Spoon/Fork Pack", "1", "piece")],
    "Kheer": [("Milk", "0.12", "gal"), ("Basmati Rice", "0.04", "lb"), ("Sugar", "0.08", "lb"), ("Heavy Cream", "0.08", "qt"), ("Ghee", "0.02", "lb"), ("Spices Mix", "0.05", "oz"), ("To-Go Container", "1", "piece"), ("Spoon/Fork Pack", "1", "piece")],
    "Family Chicken Biryani Tray": [("Basmati Rice", "2.20", "lb"), ("Chicken", "1.80", "lb"), ("Cooking Oil", "0.15", "gal"), ("Onion", "0.40", "lb"), ("Yogurt", "0.25", "lb"), ("Spices Mix", "2.00", "oz"), ("To-Go Container", "1", "piece"), ("Spoon/Fork Pack", "6", "piece")],
}
for menu_name, rows in recipes.items():
    item = menu_items[menu_name]
    RecipeIngredient.objects.filter(menu_item=item).delete()
    for ingredient_name, qty, unit in rows:
        RecipeIngredient.objects.create(
            menu_item=item,
            ingredient=ingredients[ingredient_name],
            quantity_used=Decimal(qty),
            recipe_unit=unit,
        )

start_count = InventoryCount.objects.create(
    store=store,
    business_date=start_date,
    status=InventoryCount.CLOSED,
    counted_by=owner,
    notes="Starting seeded count",
    closed_at=timezone.now(),
)
for name, qty in starting_counts.items():
    InventoryCountItem.objects.create(
        count=start_count,
        ingredient=ingredients[name],
        counted_quantity=qty,
        unit_cost_snapshot=ingredients[name].average_cost,
    )

purchase = PurchaseReceive.objects.create(
    store=store,
    vendor=vendors["Restaurant Depot"],
    invoice_number="RD-1001",
    invoice_date=today,
    status=PurchaseReceive.POSTED,
    received_by=owner,
    subtotal=Decimal("190.90"),
    total=Decimal("190.90"),
    notes="Seeded purchase test",
)
for ingredient_name, purchase_qty, total_cost in [
    ("Basmati Rice", Decimal("1"), Decimal("42.50")),
    ("Chicken", Decimal("1"), Decimal("98.00")),
    ("Cooking Oil", Decimal("1"), Decimal("36.00")),
    ("Spices Mix", Decimal("1"), Decimal("14.40")),
]:
    ing = ingredients[ingredient_name]
    inventory_qty = purchase_qty * ing.purchase_to_inventory_factor
    PurchaseReceiveItem.objects.create(
        purchase=purchase,
        ingredient=ing,
        purchase_quantity=purchase_qty,
        purchase_unit=ing.purchase_unit,
        quantity_received=inventory_qty,
        inventory_unit=ing.inventory_unit,
        unit_cost=(total_cost / inventory_qty).quantize(Decimal("0.0001")),
        total_cost=total_cost,
    )

pos, _ = POSConnection.objects.get_or_create(
    client=client,
    store=store,
    provider="csv",
    defaults={"connection_name": "Manual POS Import", "is_active": True},
)
sale = ImportedSale.objects.create(
    connection=pos,
    external_order_id="TEST-1001",
    business_date=today,
    total_amount=Decimal("60.00"),
    cash_amount=Decimal("25.00"),
    card_amount=Decimal("35.00"),
)
for item_name, qty in [("Chicken Biryani", Decimal("2")), ("Butter Chicken", Decimal("1")), ("Kheer", Decimal("2"))]:
    ImportedSaleItem.objects.create(
        sale=sale,
        external_item_id=item_name,
        item_name=item_name,
        quantity=qty,
        unit_price=menu_items[item_name].selling_price,
        mapped_menu_item=menu_items[item_name],
    )
process_sale_inventory(sale, owner)

count = InventoryCount.objects.create(store=store, business_date=today, counted_by=owner, notes="Seeded inventory count test")
actual_counts = {
    "Basmati Rice": Decimal("148"),
    "Chicken": Decimal("118"),
    "Cooking Oil": Decimal("14.8"),
    "Spices Mix": Decimal("238"),
    "To-Go Container": Decimal("493"),
}
close_inventory_count(count, [(ingredients[name], qty) for name, qty in actual_counts.items()], owner)

paidout = PaidOut.objects.create(
    store=store,
    business_date=today,
    amount=Decimal("35.00"),
    category="emergency_purchase",
    vendor_payee="Local Grocery",
    description="Extra cilantro and lemons",
    payment_source="cash",
    created_by=owner,
)
close = DailyClose.objects.create(
    store=store,
    business_date=today,
    opening_cash=Decimal("300.00"),
    cash_sales=Decimal("25.00"),
    card_sales=Decimal("35.00"),
    cash_paidouts=Decimal("35.00"),
    counted_cash=Decimal("288.00"),
    notes="Seeded daily close test",
    closed_by=owner,
    created_by=owner,
)

log_audit(
    owner,
    "quick_stop_seeded",
    "Seeded starter restaurant data, recipes, purchase, POS sale, inventory count, paid-out, and daily close.",
    client=client,
    store=store,
)

sale.refresh_from_db()
print("Seeded Quick stop store:", store.name)
print("Manager login created/updated: quickstop_manager / Quickstop@1339")
print("Vendors:", Vendor.objects.filter(client=client).count())
print("Ingredients:", Ingredient.objects.filter(client=client).count())
print("Menu items:", MenuItem.objects.filter(client=client).count())
print("Recipe rows:", RecipeIngredient.objects.filter(menu_item__client=client).count())
print("Purchase RD-1001 total:", purchase.total)
print("Sale TEST-1001 processed:", sale.processed_theoretical_usage)
print("Daily close short/over:", close.short_over)
print("Variance rows:", len(get_actual_vs_theoretical_rows(store, start_count=start_count, end_count=count)))
