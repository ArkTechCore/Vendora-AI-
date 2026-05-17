from pathlib import Path

from django.conf import settings
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from accounts.models import User
from clients.models import Client
from dailyclose.models import DailyClose
from inventory.models import Ingredient, InventoryCount, InventoryCountItem, PurchaseReceive, PurchaseReceiveItem, StockMovement
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale, ImportedSaleItem, POSConnection
from stores.models import Store
from dashboard.services import INVENTORY_PAIDOUT_CATEGORIES, OPERATING_PAIDOUT_CATEGORIES, get_actual_pos_cogs, get_theoretical_cogs


def _date_filter(qs, field, start_date=None, end_date=None):
    if start_date:
        qs = qs.filter(**{f"{field}__gte": start_date})
    if end_date:
        qs = qs.filter(**{f"{field}__lte": end_date})
    return qs


def build_report_data(user, report_type="full", store=None, start_date=None, end_date=None):
    generated_at = timezone.localtime()
    logo_path = str(Path(settings.BASE_DIR) / "static" / "img" / "vendoraops-logo.jpeg")
    if user.is_super_admin():
        value_expr = ExpressionWrapper(F("current_quantity") * F("average_cost"), output_field=DecimalField(max_digits=14, decimal_places=2))
        sales = ImportedSale.objects.all()
        if start_date or end_date:
            sales = _date_filter(sales, "business_date", start_date, end_date)
        client_rows = []
        for client in Client.objects.order_by("name"):
            client_sales = sales.filter(connection__client=client)
            ingredients = Ingredient.objects.filter(client=client)
            client_rows.append({
                "client": client.name,
                "status": client.get_status_display(),
                "sales": client_sales.aggregate(total=Sum("total_amount"))["total"] or 0,
                "orders": client_sales.count(),
                "inventory_value": ingredients.aggregate(total=Sum(value_expr))["total"] or 0,
                "inventory_items": ingredients.count(),
                "inventory_movements": StockMovement.objects.filter(ingredient__client=client).count(),
            })
        return {
            "title": "VendoraOps Platform Report",
            "report_type": "platform",
            "generated_at": generated_at,
            "business": {
                "name": "VendoraOps",
                "owner_name": "Platform Administration",
                "email": "",
                "phone": "",
                "logo_path": logo_path,
            },
            "filters": {"date_range": _date_range_label(start_date, end_date), "store": "Platform safe"},
            "platform": {
                "platform_sales_handled": sales.aggregate(total=Sum("total_amount"))["total"] or 0,
                "orders_handled": sales.count(),
                "active_clients": Client.objects.filter(status="active").count(),
                "total_clients": Client.objects.count(),
                "total_stores": Store.objects.count(),
                "pos_connections": POSConnection.objects.count(),
                "inventory_value_handled": Ingredient.objects.aggregate(total=Sum(value_expr))["total"] or 0,
                "inventory_items_handled": Ingredient.objects.count(),
                "inventory_movements_handled": StockMovement.objects.count(),
            },
            "platform_clients": client_rows,
        }

    stores = Store.objects.filter(is_active=True)
    if user.is_client_owner():
        stores = stores.filter(client=user.client)
    elif user.is_manager():
        stores = stores.filter(pk=user.store_id)
        store = user.store
    if store:
        stores = stores.filter(pk=store.pk)

    sales = ImportedSale.objects.filter(connection__store__in=stores)
    paidouts = PaidOut.objects.filter(store__in=stores)
    closes = DailyClose.objects.filter(store__in=stores)
    purchases = PurchaseReceive.objects.filter(store__in=stores)
    counts = InventoryCount.objects.filter(store__in=stores)
    ingredients = Ingredient.objects.filter(client=user.client if not user.is_super_admin() else None)
    if store:
        ingredients = ingredients.filter(store__in=[store, None])

    sales = _date_filter(sales, "business_date", start_date, end_date)
    paidouts = _date_filter(paidouts, "business_date", start_date, end_date)
    closes = _date_filter(closes, "business_date", start_date, end_date)
    purchases = _date_filter(purchases, "invoice_date", start_date, end_date)
    counts = _date_filter(counts, "business_date", start_date, end_date)
    purchase_items = PurchaseReceiveItem.objects.filter(purchase__in=purchases).select_related("purchase", "purchase__store", "purchase__vendor", "ingredient")
    count_items = InventoryCountItem.objects.filter(count__in=counts).select_related("count", "count__store", "count__counted_by", "ingredient")

    client = user.client
    value_expr = ExpressionWrapper(F("current_quantity") * F("average_cost"), output_field=DecimalField(max_digits=14, decimal_places=2))
    inventory_value = ingredients.aggregate(total=Sum(value_expr))["total"] or 0
    theoretical_cogs = get_theoretical_cogs(sales)
    actual_cogs = get_actual_pos_cogs(sales)
    food_cogs = actual_cogs or theoretical_cogs
    sales_total = sales.aggregate(total=Sum("total_amount"))["total"] or 0
    tax_collected = sales.aggregate(total=Sum("tax_amount"))["total"] or 0
    tips_collected = sales.aggregate(total=Sum("tip_amount"))["total"] or 0
    discounts = sales.aggregate(total=Sum("discount_amount"))["total"] or 0
    net_sales = sales_total - tax_collected - tips_collected
    paidouts_total = paidouts.aggregate(total=Sum("amount"))["total"] or 0
    inventory_paidouts = paidouts.filter(category__in=INVENTORY_PAIDOUT_CATEGORIES).aggregate(total=Sum("amount"))["total"] or 0
    operating_paidouts = paidouts.filter(category__in=OPERATING_PAIDOUT_CATEGORIES).aggregate(total=Sum("amount"))["total"] or 0
    uncategorized_paidouts = paidouts_total - inventory_paidouts - operating_paidouts
    operating_expenses = operating_paidouts + uncategorized_paidouts
    short_over_total = closes.aggregate(total=Sum("short_over"))["total"] or 0
    gross_profit = net_sales - food_cogs
    net_profit = gross_profit - operating_expenses + short_over_total

    return {
        "title": "VendoraOps Restaurant Report",
        "report_type": report_type,
        "generated_at": generated_at,
        "business": {
            "name": client.name,
            "owner_name": client.owner_name,
            "email": client.email,
            "phone": client.phone,
            "logo_path": logo_path,
        },
        "filters": {
            "date_range": _date_range_label(start_date, end_date),
            "store": store.name if store else "All accessible stores",
        },
        "summary": {
            "sales": sales_total,
            "net_sales": net_sales,
            "cash_sales": sales.aggregate(total=Sum("cash_amount"))["total"] or 0,
            "card_sales": sales.aggregate(total=Sum("card_amount"))["total"] or 0,
            "tax_collected": tax_collected,
            "tips_collected": tips_collected,
            "discounts": discounts,
            "theoretical_cogs": theoretical_cogs,
            "actual_cogs": actual_cogs,
            "food_cogs": food_cogs,
            "gross_profit": gross_profit,
            "paidouts": paidouts_total,
            "inventory_paidouts": inventory_paidouts,
            "operating_paidouts": operating_paidouts,
            "uncategorized_paidouts": uncategorized_paidouts,
            "operating_expenses": operating_expenses,
            "cash_paidouts": paidouts.filter(payment_source="cash").aggregate(total=Sum("amount"))["total"] or 0,
            "short_over": short_over_total,
            "net_profit": net_profit,
            "inventory_value": inventory_value,
            "low_stock_count": ingredients.filter(current_quantity__lte=F("low_stock_level")).count(),
            "processed_sales": sales.filter(processed_inventory=True).count(),
            "unprocessed_sales": sales.filter(processed_inventory=False).count(),
        },
        "sales": sales[:40],
        "paidouts": paidouts.select_related("store", "created_by")[:40],
        "daily_closes": closes.select_related("store", "closed_by")[:40],
        "purchases": purchases.select_related("store", "vendor", "received_by")[:40],
        "purchase_items": purchase_items[:80],
        "low_stock": ingredients.filter(current_quantity__lte=F("low_stock_level"))[:40],
        "inventory_counts": counts.select_related("store", "counted_by")[:40],
        "inventory_count_items": count_items[:120],
    }


def _date_range_label(start_date, end_date):
    if start_date and end_date:
        return f"{start_date} to {end_date}"
    if start_date:
        return f"From {start_date}"
    if end_date:
        return f"Through {end_date}"
    return "All dates"
