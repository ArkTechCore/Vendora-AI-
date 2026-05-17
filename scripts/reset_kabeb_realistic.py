from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import random

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import User
from clients.models import Client
from dailyclose.models import DailyClose
from inventory.models import Ingredient, InventoryCount, InventoryCountItem, MenuItem, PurchaseReceive, PurchaseReceiveItem, RecipeIngredient, StockMovement, Vendor
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale, ImportedSaleItem, POSConnection
from pos_integrations.services import process_sale_inventory
from stores.models import Store


random.seed(20260510)
MONEY = Decimal("0.01")


def dollars(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def reset_kabeb():
    client = Client.objects.get(name__iexact="Kabeb Station")
    store = Store.objects.filter(client=client, is_active=True).first()
    owner = User.objects.filter(client=client, role=User.CLIENT_OWNER).first()
    if not store or not owner:
        raise RuntimeError("Kabeb Station needs an active store and owner.")

    ImportedSaleItem.objects.filter(sale__connection__client=client).delete()
    ImportedSale.objects.filter(connection__client=client).delete()
    POSConnection.objects.filter(client=client).delete()
    PurchaseReceiveItem.objects.filter(purchase__store__client=client).delete()
    PurchaseReceive.objects.filter(store__client=client).delete()
    PaidOut.objects.filter(store__client=client).delete()
    DailyClose.objects.filter(store__client=client).delete()
    InventoryCountItem.objects.filter(count__store__client=client).delete()
    InventoryCount.objects.filter(store__client=client).delete()
    StockMovement.objects.filter(ingredient__client=client).delete()
    RecipeIngredient.objects.filter(menu_item__client=client).delete()
    MenuItem.objects.filter(client=client).delete()
    Ingredient.objects.filter(client=client).delete()
    Vendor.objects.filter(client=client).delete()

    vendors = {}
    for name, note in [
        ("Halal Meat Market", "Lamb, chicken, beef"),
        ("Fresh Levant Produce", "Produce and herbs"),
        ("Spice Route Supply", "Indian and Middle Eastern spices"),
        ("Basmati Bakery Supply", "Rice, naan, pita, packaging"),
    ]:
        vendors[name] = Vendor.objects.create(client=client, name=name, contact_name="Sales Desk", phone="555-0400", address=note, is_active=True)

    ingredient_specs = [
        ("Lamb Cubes", "Meat", "lb", "case", "5.05", "420", "85", "Halal Meat Market"),
        ("Ground Lamb", "Meat", "lb", "case", "4.55", "220", "45", "Halal Meat Market"),
        ("Chicken Thigh", "Meat", "lb", "case", "2.25", "620", "120", "Halal Meat Market"),
        ("Beef Sirloin", "Meat", "lb", "case", "5.35", "180", "45", "Halal Meat Market"),
        ("Basmati Rice", "Rice", "lb", "bag", "0.82", "850", "160", "Basmati Bakery Supply"),
        ("Pita Bread", "Bread", "piece", "case", "0.25", "1200", "220", "Basmati Bakery Supply"),
        ("Naan", "Bread", "piece", "case", "0.40", "820", "160", "Basmati Bakery Supply"),
        ("Chickpeas", "Dry Goods", "lb", "bag", "0.96", "260", "55", "Basmati Bakery Supply"),
        ("Tahini", "Sauce", "lb", "tub", "2.95", "95", "22", "Spice Route Supply"),
        ("Yogurt", "Dairy", "lb", "tub", "1.35", "160", "35", "Fresh Levant Produce"),
        ("Onion", "Produce", "lb", "bag", "0.62", "300", "60", "Fresh Levant Produce"),
        ("Tomato", "Produce", "lb", "box", "0.86", "260", "55", "Fresh Levant Produce"),
        ("Cucumber", "Produce", "lb", "box", "0.78", "190", "40", "Fresh Levant Produce"),
        ("Mint Cilantro Mix", "Herbs", "oz", "case", "0.24", "520", "100", "Fresh Levant Produce"),
        ("Ginger Garlic Paste", "Spice", "lb", "tub", "1.70", "85", "18", "Spice Route Supply"),
        ("Garam Masala", "Spice", "oz", "bag", "0.20", "700", "120", "Spice Route Supply"),
        ("Shawarma Spice", "Spice", "oz", "bag", "0.22", "760", "130", "Spice Route Supply"),
        ("Cooking Oil", "Oil", "gal", "jug", "7.20", "95", "20", "Basmati Bakery Supply"),
        ("To-Go Bowl", "Packaging", "piece", "case", "0.12", "2800", "550", "Basmati Bakery Supply"),
        ("Wrap Foil", "Packaging", "piece", "case", "0.06", "3600", "700", "Basmati Bakery Supply"),
    ]
    ingredients = {}
    for name, category, unit, purchase_unit, cost, qty, low, vendor_name in ingredient_specs:
        ingredient = Ingredient.objects.create(
            client=client,
            store=store,
            vendor=vendors[vendor_name],
            category=category,
            name=name,
            unit=unit,
            purchase_unit=purchase_unit,
            inventory_unit=unit,
            recipe_unit=unit,
            purchase_to_inventory_factor=Decimal("1"),
            inventory_to_recipe_factor=Decimal("1"),
            current_quantity=Decimal(qty),
            low_stock_level=Decimal(low),
            cost_per_unit=Decimal(cost),
            average_cost=Decimal(cost),
            last_cost=Decimal(cost),
            is_active=True,
        )
        StockMovement.objects.create(
            ingredient=ingredient,
            movement_type=StockMovement.ADJUSTMENT,
            quantity=Decimal(qty),
            note="Realistic opening inventory for Kabeb Station",
            created_by=owner,
        )
        ingredients[name] = ingredient

    menu_specs = [
        ("Lamb Kabeb Plate", "16.99", [("Lamb Cubes", ".42"), ("Basmati Rice", ".42"), ("Yogurt", ".05"), ("Onion", ".08"), ("Tomato", ".08"), ("Shawarma Spice", ".45"), ("To-Go Bowl", "1")]),
        ("Chicken Shawarma Wrap", "11.99", [("Chicken Thigh", ".34"), ("Pita Bread", "1"), ("Tahini", ".04"), ("Cucumber", ".07"), ("Tomato", ".07"), ("Shawarma Spice", ".38"), ("Wrap Foil", "1")]),
        ("Beef Seekh Kabab", "14.49", [("Beef Sirloin", ".34"), ("Naan", "1"), ("Onion", ".05"), ("Mint Cilantro Mix", ".18"), ("Garam Masala", ".32"), ("Wrap Foil", "1")]),
        ("Hyderabadi Chicken Biryani", "13.99", [("Chicken Thigh", ".32"), ("Basmati Rice", ".48"), ("Yogurt", ".07"), ("Ginger Garlic Paste", ".05"), ("Garam Masala", ".40"), ("Cooking Oil", ".025"), ("To-Go Bowl", "1")]),
        ("Mutton Biryani", "16.99", [("Lamb Cubes", ".38"), ("Basmati Rice", ".48"), ("Yogurt", ".07"), ("Ginger Garlic Paste", ".05"), ("Garam Masala", ".44"), ("Cooking Oil", ".025"), ("To-Go Bowl", "1")]),
        ("Butter Chicken Bowl", "13.49", [("Chicken Thigh", ".32"), ("Basmati Rice", ".36"), ("Tomato", ".15"), ("Yogurt", ".07"), ("Garam Masala", ".30"), ("Cooking Oil", ".02"), ("To-Go Bowl", "1")]),
        ("Falafel Hummus Bowl", "10.99", [("Chickpeas", ".32"), ("Tahini", ".07"), ("Pita Bread", "1"), ("Cucumber", ".09"), ("Tomato", ".09"), ("Mint Cilantro Mix", ".22"), ("To-Go Bowl", "1")]),
        ("Mixed Grill Family Tray", "54.99", [("Lamb Cubes", "1.10"), ("Chicken Thigh", "1.25"), ("Beef Sirloin", ".65"), ("Basmati Rice", "2.10"), ("Naan", "4"), ("Shawarma Spice", "1.80"), ("Garam Masala", ".85"), ("To-Go Bowl", "2")]),
    ]
    menu_items = []
    for name, price, rows in menu_specs:
        item = MenuItem.objects.create(
            client=client,
            store=store,
            category="Middle Eastern / Indian",
            name=name,
            external_pos_name=name,
            external_pos_id=name,
            selling_price=Decimal(price),
            target_food_cost_percentage=Decimal("32"),
            is_active=True,
        )
        for ingredient_name, qty in rows:
            RecipeIngredient.objects.create(menu_item=item, ingredient=ingredients[ingredient_name], quantity_used=Decimal(qty), recipe_unit=ingredients[ingredient_name].recipe_unit)
        menu_items.append(item)

    pos = POSConnection.objects.create(client=client, store=store, provider="csv", connection_name="Kabeb Station POS", environment="production", is_active=True, auto_sync_enabled=True, sync_status="success")

    today = timezone.localdate()
    start_date = today - timedelta(days=29)
    totals = {"sales": 0, "sale_items": 0, "paidouts": 0, "purchases": 0, "daily_closes": 0, "counts": 0}

    for day_index in range(30):
        business_date = start_date + timedelta(days=day_index)
        weekday = business_date.weekday()
        orders_target = random.randint(48, 62) if weekday < 5 else random.randint(72, 92)
        daily_cash = Decimal("0")
        daily_card = Decimal("0")
        daily_tax = Decimal("0")
        daily_tip = Decimal("0")

        if weekday in {0, 3}:
            purchase = PurchaseReceive.objects.create(
                store=store,
                vendor=random.choice(list(vendors.values())),
                invoice_number=f"KS-{business_date:%Y%m%d}",
                invoice_date=business_date,
                status=PurchaseReceive.POSTED,
                received_by=owner,
                subtotal=Decimal("0"),
                total=Decimal("0"),
                notes="Regular weekly receive",
            )
            total = Decimal("0")
            purchase_ingredients = random.sample(list(ingredients.values()), 7 if weekday == 0 else 5)
            for ingredient in purchase_ingredients:
                qty = Decimal(random.randint(8, 90))
                unit_cost = Decimal(str(ingredient.average_cost))
                line_total = dollars(qty * unit_cost)
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
            totals["purchases"] += 1

        for order_num in range(orders_target):
            chosen = random.choices(menu_items, weights=[15, 29, 12, 24, 13, 18, 14, 3], k=random.choice([1, 1, 1, 2, 2, 3]))
            subtotal = Decimal("0")
            sale = ImportedSale.objects.create(
                connection=pos,
                external_order_id=f"KS-{business_date:%Y%m%d}-{order_num:03d}",
                business_date=business_date,
                total_amount=Decimal("0"),
                cash_amount=Decimal("0"),
                card_amount=Decimal("0"),
                tax_amount=Decimal("0"),
                tip_amount=Decimal("0"),
                discount_amount=Decimal("0"),
                status="imported",
            )
            for item in chosen:
                qty = Decimal(random.choice([1, 1, 1, 2]))
                ImportedSaleItem.objects.create(sale=sale, external_item_id=item.external_pos_id, item_name=item.name, quantity=qty, unit_price=item.selling_price, mapped_menu_item=item)
                subtotal += item.selling_price * qty
                totals["sale_items"] += 1
            discount = dollars(subtotal * Decimal("0.08")) if random.random() < 0.06 else Decimal("0")
            taxable = subtotal - discount
            tax = dollars(taxable * Decimal("0.06625"))
            tip = dollars(taxable * Decimal(str(random.choice([0, 0, 0, 0.08, 0.12, 0.15]))))
            total = dollars(taxable + tax + tip)
            cash = total if random.random() < 0.34 else Decimal("0")
            sale.total_amount = total
            sale.cash_amount = cash
            sale.card_amount = total - cash
            sale.tax_amount = tax
            sale.tip_amount = tip
            sale.discount_amount = discount
            sale.save(update_fields=["total_amount", "cash_amount", "card_amount", "tax_amount", "tip_amount", "discount_amount"])
            process_sale_inventory(sale, owner)
            daily_cash += cash
            daily_card += total - cash
            daily_tax += tax
            daily_tip += tip
            totals["sales"] += 1

        paidout_rows = []
        if random.random() < 0.55:
            paidout_rows.append(("cleaning", dollars(random.randint(24, 68)), "Cleaning supplies"))
        if random.random() < 0.28:
            paidout_rows.append(("gas", dollars(random.randint(18, 44)), "Delivery fuel"))
        if random.random() < 0.22:
            paidout_rows.append(("maintenance", dollars(random.randint(55, 180)), "Small equipment repair"))
        if random.random() < 0.18:
            paidout_rows.append(("emergency_purchase", dollars(random.randint(35, 125)), "Emergency ingredient run"))
        for idx, (category, amount, description) in enumerate(paidout_rows):
            PaidOut.objects.create(
                store=store,
                business_date=business_date,
                amount=amount,
                category=category,
                description=description,
                vendor_payee="Local Supplier",
                payment_source=random.choice(["cash", "card"]),
                receipt_number=f"KSPO-{business_date:%Y%m%d}-{idx}",
                created_by=owner,
            )
            totals["paidouts"] += 1

        cash_paidouts = sum((p.amount for p in PaidOut.objects.filter(store=store, business_date=business_date, payment_source="cash")), Decimal("0"))
        opening_cash = Decimal("500.00")
        expected_cash = opening_cash + daily_cash - cash_paidouts
        counted_cash = expected_cash + Decimal(random.choice([-9, -4, -2, 0, 0, 1, 3, 5]))
        DailyClose.objects.create(
            store=store,
            business_date=business_date,
            opening_cash=opening_cash,
            cash_sales=daily_cash,
            card_sales=daily_card,
            cash_paidouts=cash_paidouts,
            counted_cash=counted_cash,
            notes="Normal daily close",
            closed_by=owner,
            created_by=owner,
        )
        totals["daily_closes"] += 1

        if weekday == 6:
            count = InventoryCount.objects.create(store=store, business_date=business_date, status=InventoryCount.CLOSED, counted_by=owner, notes="Weekly physical count", closed_at=timezone.now())
            for ingredient in ingredients.values():
                InventoryCountItem.objects.create(count=count, ingredient=ingredient, counted_quantity=max(Decimal("0"), ingredient.current_quantity + Decimal(random.randint(-3, 3))), unit_cost_snapshot=ingredient.average_cost)
            totals["counts"] += 1

    sales = ImportedSale.objects.filter(connection__client=client)
    paidouts = PaidOut.objects.filter(store__client=client)
    purchases = PurchaseReceive.objects.filter(store__client=client)
    totals.update({
        "client_id": client.id,
        "store_id": store.id,
        "sales_total": sales.aggregate(total=Sum("total_amount"))["total"],
        "tax_total": sales.aggregate(total=Sum("tax_amount"))["total"],
        "tip_total": sales.aggregate(total=Sum("tip_amount"))["total"],
        "paidout_total": paidouts.aggregate(total=Sum("amount"))["total"],
        "purchase_total": purchases.aggregate(total=Sum("total"))["total"],
        "stock_movements": StockMovement.objects.filter(ingredient__client=client).count(),
    })
    return totals


with transaction.atomic():
    print(reset_kabeb())
