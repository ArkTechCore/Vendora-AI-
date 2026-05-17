from datetime import timedelta
from decimal import Decimal
import random
import time

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import User
from clients.models import Client
from dailyclose.models import DailyClose
from inventory.models import Ingredient, InventoryCount, InventoryCountItem, PurchaseReceive, PurchaseReceiveItem, StockMovement, Vendor
from paidouts.models import PaidOut
from stores.models import Store


PREFIX = "OPSLOAD"
random.seed(4401)


def owner_for(client):
    owner = User.objects.filter(client=client, role=User.CLIENT_OWNER, is_active=True).first()
    if owner:
        return owner
    return User.objects.filter(is_superuser=True).first()


def cleanup():
    PaidOut.objects.filter(receipt_number__startswith=PREFIX).delete()
    PurchaseReceiveItem.objects.filter(purchase__invoice_number__startswith=PREFIX).delete()
    PurchaseReceive.objects.filter(invoice_number__startswith=PREFIX).delete()
    InventoryCountItem.objects.filter(count__notes__startswith=PREFIX).delete()
    InventoryCount.objects.filter(notes__startswith=PREFIX).delete()
    StockMovement.objects.filter(note__startswith=PREFIX).delete()


def ensure_vendor(client):
    vendor, _ = Vendor.objects.update_or_create(
        client=client,
        name=f"{PREFIX} Stress Supplier",
        defaults={"contact_name": "Stress Desk", "phone": "555-9900", "address": "Load testing supplier", "is_active": True},
    )
    return vendor


def amount_for(client_index, day_index, item_index):
    dollars = 7 + (client_index * 1000) + (day_index * 37) + item_index
    cents = (13 + item_index * 7 + day_index) % 100
    return Decimal(f"{dollars}.{cents:02d}")


@transaction.atomic
def run(days=35, paidouts_per_day=22, purchases_per_day=3, items_per_purchase=10, adjustments_per_day=18):
    cleanup()
    today = timezone.localdate()
    clients = list(Client.objects.filter(status=Client.ACTIVE).order_by("id"))
    if not clients:
        raise RuntimeError("No active clients found.")

    totals = {
        "clients": len(clients),
        "paidouts": 0,
        "purchases": 0,
        "purchase_items": 0,
        "stock_movements": 0,
        "inventory_counts": 0,
        "daily_closes": 0,
    }

    for client_index, client in enumerate(clients):
        store = Store.objects.filter(client=client, is_active=True).first()
        user = owner_for(client)
        if not store or not user:
            continue
        vendor = ensure_vendor(client)
        ingredients = list(Ingredient.objects.filter(client=client, is_active=True, store__in=[store, None]).order_by("id"))
        if not ingredients:
            continue

        for day_index in range(days):
            business_date = today - timedelta(days=days - day_index - 1)

            paidouts = []
            for item_index in range(paidouts_per_day):
                paidouts.append(PaidOut(
                    store=store,
                    business_date=business_date,
                    amount=amount_for(client_index, day_index, item_index),
                    category=random.choice(["groceries", "meat", "vegetables", "cleaning", "maintenance", "gas", "emergency_purchase"]),
                    description=f"{PREFIX} stress paid-out {business_date} #{item_index}",
                    vendor_payee=f"{PREFIX} Vendor {client_index}-{day_index}-{item_index}",
                    payment_source=random.choice(["cash", "card", "bank"]),
                    receipt_number=f"{PREFIX}-PO-{client.id}-{day_index:03d}-{item_index:03d}",
                    created_by=user,
                    approved=True,
                    locked=True,
                ))
            PaidOut.objects.bulk_create(paidouts, batch_size=250)
            totals["paidouts"] += len(paidouts)

            for purchase_index in range(purchases_per_day):
                purchase = PurchaseReceive.objects.create(
                    store=store,
                    vendor=vendor,
                    invoice_number=f"{PREFIX}-INV-{client.id}-{day_index:03d}-{purchase_index:03d}",
                    invoice_date=business_date,
                    status=PurchaseReceive.POSTED,
                    subtotal=Decimal("0.00"),
                    total=Decimal("0.00"),
                    received_by=user,
                    notes=f"{PREFIX} purchase stress",
                )
                purchase_total = Decimal("0.00")
                for ingredient in random.sample(ingredients, min(items_per_purchase, len(ingredients))):
                    qty = Decimal(random.randint(3, 90))
                    unit_cost = Decimal(str(ingredient.average_cost or ingredient.cost_per_unit or 1)).quantize(Decimal("0.0001"))
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
                    purchase_total += line_total
                    totals["purchase_items"] += 1
                purchase.subtotal = purchase_total
                purchase.total = purchase_total
                purchase.save(update_fields=["subtotal", "total"])
                totals["purchases"] += 1

            for movement_index in range(adjustments_per_day):
                ingredient = random.choice(ingredients)
                qty = Decimal(random.randint(1, 35))
                StockMovement.objects.create(
                    ingredient=ingredient,
                    movement_type=random.choice([StockMovement.WASTE, StockMovement.USAGE, StockMovement.RECEIVE]),
                    quantity=qty,
                    note=f"{PREFIX} stress movement {business_date} #{movement_index}",
                    created_by=user,
                )
                totals["stock_movements"] += 1

            if day_index % 7 == 0:
                count, _created = InventoryCount.objects.update_or_create(
                    store=store,
                    business_date=business_date,
                    defaults={
                        "status": InventoryCount.CLOSED,
                        "counted_by": user,
                        "notes": f"{PREFIX} weekly stress count",
                        "closed_at": timezone.now(),
                    },
                )
                count.items.all().delete()
                for ingredient in ingredients[:80]:
                    InventoryCountItem.objects.create(
                        count=count,
                        ingredient=ingredient,
                        counted_quantity=max(Decimal("0"), ingredient.current_quantity + Decimal(random.randint(-5, 5))),
                        unit_cost_snapshot=ingredient.average_cost,
                    )
                totals["inventory_counts"] += 1

            if day_index >= days - 10:
                DailyClose.objects.get_or_create(
                    store=store,
                    business_date=business_date,
                    defaults={
                        "opening_cash": Decimal("500.00"),
                        "cash_sales": Decimal(random.randint(300, 1700)),
                        "card_sales": Decimal(random.randint(700, 3200)),
                        "cash_paidouts": Decimal(random.randint(20, 260)),
                        "counted_cash": Decimal(random.randint(450, 2200)),
                        "notes": f"{PREFIX} stress daily close",
                        "closed_by": user,
                        "created_by": user,
                    },
                )
                totals["daily_closes"] += 1

    totals["paidout_total"] = PaidOut.objects.filter(receipt_number__startswith=PREFIX).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    totals["purchase_total"] = PurchaseReceive.objects.filter(invoice_number__startswith=PREFIX).aggregate(total=Sum("total"))["total"] or Decimal("0")
    return totals


start = time.perf_counter()
result = run()
result["seconds"] = round(time.perf_counter() - start, 2)
print(result)
