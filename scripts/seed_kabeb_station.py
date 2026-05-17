from datetime import timedelta
from decimal import Decimal
import random

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from clients.models import Client
from inventory.models import Ingredient, MenuItem, PurchaseReceive, PurchaseReceiveItem, RecipeIngredient, StockMovement, Vendor
from pos_integrations.models import ImportedSale, ImportedSaleItem, POSConnection
from pos_integrations.services import process_sale_inventory
from stores.models import Store


PREFIX = "KABEBLOAD"
random.seed(786)


@transaction.atomic
def run(days=60, orders_per_day=20):
    client, _ = Client.objects.update_or_create(
        name="Kabeb Station",
        defaults={
            "owner_name": "Kabeb Station Owner",
            "email": "owner@kabebstation.example",
            "phone": "555-0222",
            "street_address": "410 Market Street",
            "city": "Jersey City",
            "state": "NJ",
            "postal_code": "07302",
            "country": "US",
            "address": "410 Market Street, Jersey City, NJ 07302, US",
            "status": Client.ACTIVE,
        },
    )
    store, _ = Store.objects.update_or_create(
        client=client,
        code="KS-JC",
        defaults={
            "name": "Kabeb Station JC",
            "address": "410 Market Street, Jersey City, NJ 07302",
            "phone": "555-0222",
            "is_active": True,
        },
    )
    owner, _ = User.objects.update_or_create(
        username="kabeb_owner",
        defaults={
            "email": "owner@kabebstation.example",
            "first_name": "Kabeb",
            "last_name": "Owner",
            "role": User.CLIENT_OWNER,
            "client": client,
            "store": None,
            "is_active": True,
        },
    )
    owner.set_password("KabebStation@1339")
    owner.save()

    ImportedSaleItem.objects.filter(sale__connection__client=client, sale__external_order_id__startswith=PREFIX).delete()
    ImportedSale.objects.filter(connection__client=client, external_order_id__startswith=PREFIX).delete()
    PurchaseReceiveItem.objects.filter(purchase__store=store, purchase__invoice_number__startswith=PREFIX).delete()
    PurchaseReceive.objects.filter(store=store, invoice_number__startswith=PREFIX).delete()
    StockMovement.objects.filter(ingredient__client=client, note__startswith=PREFIX).delete()
    StockMovement.objects.filter(ingredient__client=client, source_sale_id__startswith=PREFIX).delete()

    vendors = {}
    for name, category in [
        ("Kabeb Halal Meats", "Lamb, chicken, beef"),
        ("Levant Produce", "Herbs, vegetables, citrus"),
        ("Spice Route Imports", "Middle Eastern and Indian spices"),
        ("Basmati & Bakery Supply", "Rice, naan, pita, dry goods"),
        ("Packaging Hub", "Bowls, wraps, trays"),
    ]:
        vendors[name], _ = Vendor.objects.update_or_create(
            client=client,
            name=name,
            defaults={"contact_name": "Sales Desk", "phone": "555-0300", "address": category, "is_active": True},
        )

    ingredient_rows = [
        ("Lamb Cubes", "Meat", "lb", "case", "4.95", "2600", "350", "Kabeb Halal Meats"),
        ("Ground Lamb", "Meat", "lb", "case", "4.40", "1900", "260", "Kabeb Halal Meats"),
        ("Chicken Thigh", "Meat", "lb", "case", "2.15", "3600", "500", "Kabeb Halal Meats"),
        ("Beef Sirloin", "Meat", "lb", "case", "5.20", "1500", "220", "Kabeb Halal Meats"),
        ("Basmati Rice", "Rice", "lb", "bag", "0.78", "5200", "700", "Basmati & Bakery Supply"),
        ("Pita Bread", "Bread", "piece", "case", "0.24", "7200", "1200", "Basmati & Bakery Supply"),
        ("Naan", "Bread", "piece", "case", "0.38", "5400", "900", "Basmati & Bakery Supply"),
        ("Chickpeas", "Dry Goods", "lb", "bag", "0.92", "2200", "320", "Basmati & Bakery Supply"),
        ("Tahini", "Sauce", "lb", "tub", "2.85", "850", "130", "Spice Route Imports"),
        ("Yogurt", "Dairy", "lb", "tub", "1.28", "1100", "180", "Levant Produce"),
        ("Onion", "Produce", "lb", "bag", "0.58", "2400", "320", "Levant Produce"),
        ("Tomato", "Produce", "lb", "box", "0.82", "2100", "300", "Levant Produce"),
        ("Cucumber", "Produce", "lb", "box", "0.74", "1600", "230", "Levant Produce"),
        ("Mint Cilantro Mix", "Herbs", "oz", "case", "0.22", "4100", "700", "Levant Produce"),
        ("Ginger Garlic Paste", "Spice", "lb", "tub", "1.65", "900", "150", "Spice Route Imports"),
        ("Garam Masala", "Spice", "oz", "bag", "0.19", "5200", "850", "Spice Route Imports"),
        ("Shawarma Spice", "Spice", "oz", "bag", "0.21", "5400", "850", "Spice Route Imports"),
        ("Saffron Cardamom Mix", "Spice", "oz", "bag", "1.80", "900", "120", "Spice Route Imports"),
        ("Cooking Oil", "Oil", "gal", "jug", "7.05", "760", "110", "Basmati & Bakery Supply"),
        ("To-Go Bowl", "Packaging", "piece", "case", "0.12", "18000", "3000", "Packaging Hub"),
        ("Wrap Foil", "Packaging", "piece", "case", "0.06", "22000", "4000", "Packaging Hub"),
    ]
    ingredients = {}
    for name, category, unit, purchase_unit, cost, qty, low, vendor_name in ingredient_rows:
        ingredient, _ = Ingredient.objects.update_or_create(
            client=client,
            store=store,
            name=name,
            defaults={
                "category": category,
                "vendor": vendors[vendor_name],
                "inventory_unit": unit,
                "recipe_unit": unit,
                "purchase_unit": purchase_unit,
                "purchase_to_inventory_factor": Decimal("1"),
                "inventory_to_recipe_factor": Decimal("1"),
                "current_quantity": Decimal(qty),
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
            note=f"{PREFIX} opening inventory",
            created_by=owner,
        )
        ingredients[name] = ingredient

    menu_specs = [
        ("Lamb Kabeb Plate", "16.99", [("Lamb Cubes", ".42"), ("Basmati Rice", ".45"), ("Yogurt", ".06"), ("Onion", ".08"), ("Tomato", ".08"), ("Shawarma Spice", ".55"), ("To-Go Bowl", "1")]),
        ("Chicken Shawarma Wrap", "11.99", [("Chicken Thigh", ".36"), ("Pita Bread", "1"), ("Tahini", ".05"), ("Cucumber", ".08"), ("Tomato", ".08"), ("Shawarma Spice", ".45"), ("Wrap Foil", "1")]),
        ("Beef Seekh Kabab", "14.99", [("Beef Sirloin", ".38"), ("Naan", "1"), ("Onion", ".06"), ("Mint Cilantro Mix", ".20"), ("Garam Masala", ".35"), ("Wrap Foil", "1")]),
        ("Hyderabadi Chicken Biryani", "13.99", [("Chicken Thigh", ".34"), ("Basmati Rice", ".50"), ("Yogurt", ".08"), ("Ginger Garlic Paste", ".05"), ("Garam Masala", ".45"), ("Saffron Cardamom Mix", ".05"), ("Cooking Oil", ".03"), ("To-Go Bowl", "1")]),
        ("Mutton Biryani", "16.99", [("Lamb Cubes", ".40"), ("Basmati Rice", ".50"), ("Yogurt", ".08"), ("Ginger Garlic Paste", ".05"), ("Garam Masala", ".48"), ("Saffron Cardamom Mix", ".06"), ("Cooking Oil", ".03"), ("To-Go Bowl", "1")]),
        ("Butter Chicken Bowl", "13.49", [("Chicken Thigh", ".34"), ("Basmati Rice", ".38"), ("Tomato", ".16"), ("Yogurt", ".08"), ("Garam Masala", ".35"), ("Cooking Oil", ".02"), ("To-Go Bowl", "1")]),
        ("Falafel Hummus Bowl", "10.99", [("Chickpeas", ".34"), ("Tahini", ".08"), ("Pita Bread", "1"), ("Cucumber", ".10"), ("Tomato", ".10"), ("Mint Cilantro Mix", ".25"), ("To-Go Bowl", "1")]),
        ("Mixed Grill Family Tray", "54.99", [("Lamb Cubes", "1.25"), ("Chicken Thigh", "1.45"), ("Beef Sirloin", ".85"), ("Basmati Rice", "2.4"), ("Naan", "4"), ("Shawarma Spice", "2.2"), ("Garam Masala", "1.1"), ("To-Go Bowl", "2")]),
    ]
    menu_items = []
    for name, price, recipe_rows in menu_specs:
        item, _ = MenuItem.objects.update_or_create(
            client=client,
            store=store,
            name=name,
            defaults={"category": "Middle Eastern / Indian", "selling_price": Decimal(price), "external_pos_name": name, "external_pos_id": name, "is_active": True},
        )
        RecipeIngredient.objects.filter(menu_item=item).delete()
        for ingredient_name, qty in recipe_rows:
            RecipeIngredient.objects.create(menu_item=item, ingredient=ingredients[ingredient_name], quantity_used=Decimal(qty), recipe_unit=ingredients[ingredient_name].recipe_unit)
        menu_items.append(item)

    pos, _ = POSConnection.objects.update_or_create(
        client=client,
        store=store,
        provider="csv",
        defaults={"connection_name": "Kabeb Station POS Import", "is_active": True, "auto_sync_enabled": True, "sync_status": "success"},
    )

    today = timezone.localdate()
    sales_created = 0
    sale_items_created = 0
    purchases_created = 0
    for day_index in range(days):
        business_date = today - timedelta(days=days - day_index - 1)
        if day_index % 5 == 0:
            purchase = PurchaseReceive.objects.create(
                store=store,
                vendor=random.choice(list(vendors.values())),
                invoice_number=f"{PREFIX}-INV-{day_index:03d}",
                invoice_date=business_date,
                status=PurchaseReceive.POSTED,
                received_by=owner,
                subtotal=Decimal("0"),
                total=Decimal("0"),
                notes=f"{PREFIX} bulk purchase",
            )
            total = Decimal("0")
            for ingredient in random.sample(list(ingredients.values()), 7):
                qty = Decimal(random.randint(35, 220))
                line_total = (qty * ingredient.average_cost).quantize(Decimal("0.01"))
                PurchaseReceiveItem.objects.create(
                    purchase=purchase,
                    ingredient=ingredient,
                    purchase_quantity=qty,
                    purchase_unit=ingredient.purchase_unit,
                    quantity_received=qty,
                    inventory_unit=ingredient.inventory_unit,
                    unit_cost=ingredient.average_cost,
                    total_cost=line_total,
                )
                total += line_total
            purchase.subtotal = total
            purchase.total = total
            purchase.save(update_fields=["subtotal", "total"])
            purchases_created += 1

        for order_num in range(orders_per_day):
            chosen = random.choices(menu_items, weights=[20, 34, 18, 32, 19, 28, 16, 5], k=random.randint(1, 4))
            sale = ImportedSale.objects.create(
                connection=pos,
                external_order_id=f"{PREFIX}-{business_date:%Y%m%d}-{order_num:03d}",
                business_date=business_date,
                total_amount=Decimal("0"),
                cash_amount=Decimal("0"),
                card_amount=Decimal("0"),
                status="imported",
            )
            total = Decimal("0")
            for item in chosen:
                qty = Decimal(random.choice([1, 1, 1, 2, 2, 3]))
                ImportedSaleItem.objects.create(
                    sale=sale,
                    external_item_id=item.external_pos_id,
                    item_name=item.name,
                    quantity=qty,
                    unit_price=item.selling_price,
                    mapped_menu_item=item,
                )
                total += item.selling_price * qty
                sale_items_created += 1
            cash = total if random.random() < 0.33 else Decimal("0")
            sale.total_amount = total
            sale.cash_amount = cash
            sale.card_amount = total - cash
            sale.save(update_fields=["total_amount", "cash_amount", "card_amount"])
            process_sale_inventory(sale, owner)
            sales_created += 1

    return {
        "client_id": client.id,
        "client": client.name,
        "store_id": store.id,
        "store": store.name,
        "owner_login": "kabeb_owner / KabebStation@1339",
        "sales": sales_created,
        "sale_items": sale_items_created,
        "purchases": purchases_created,
        "ingredients": Ingredient.objects.filter(client=client).count(),
        "menu_items": MenuItem.objects.filter(client=client).count(),
        "stock_movements": StockMovement.objects.filter(ingredient__client=client, source_sale_id__startswith=PREFIX).count(),
    }


print(run())
