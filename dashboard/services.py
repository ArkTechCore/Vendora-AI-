from calendar import monthrange
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import ExtractHour
from django.utils import timezone

from accounts.models import User
from clients.models import Client
from dailyclose.models import DailyClose
from inventory.models import Ingredient, InventoryCount, MenuItem, PurchaseReceive, StockMovement, Vendor
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale, POSConnection
from pos_integrations.models import ImportedSaleItem
from stores.models import Store
from .smart_signals import get_smart_signals

INVENTORY_PAIDOUT_CATEGORIES = {"groceries", "meat", "vegetables", "emergency_purchase"}
OPERATING_PAIDOUT_CATEGORIES = {"cleaning", "maintenance", "gas", "utilities", "refund", "other"}


def get_low_stock_items(user):
    qs = Ingredient.objects.filter(is_active=True, current_quantity__lte=F("low_stock_level"))
    if user.is_super_admin():
        return qs
    if user.is_client_owner():
        return qs.filter(client=user.client)
    return qs.filter(store=user.store)


def get_inventory_value(user):
    qs = Ingredient.objects.filter(is_active=True)
    if user.is_client_owner():
        qs = qs.filter(client=user.client)
    elif user.is_manager():
        qs = qs.filter(client=user.client, store__in=[user.store, None])
    value_expr = ExpressionWrapper(F("current_quantity") * F("average_cost"), output_field=DecimalField(max_digits=14, decimal_places=2))
    return qs.aggregate(total=Sum(value_expr))["total"] or 0

def get_dashboard_stats(user):
    today = timezone.localdate()
    week_start = today - timedelta(days=6)
    low_stock = get_low_stock_items(user)
    if user.is_super_admin():
        value_expr = ExpressionWrapper(F("current_quantity") * F("average_cost"), output_field=DecimalField(max_digits=14, decimal_places=2))
        return {
            "platform sales": ImportedSale.objects.aggregate(total=Sum("total_amount"))["total"] or 0,
            "total clients": Client.objects.count(),
            "active clients": Client.objects.filter(status="active").count(),
            "total stores": Store.objects.count(),
            "total POS connections": POSConnection.objects.count(),
            "sales processed": ImportedSale.objects.filter(processed_inventory=True).count(),
            "inventory items": Ingredient.objects.count(),
            "inventory handled": Ingredient.objects.aggregate(total=Sum(value_expr))["total"] or 0,
            "inventory movements": StockMovement.objects.count(),
        }
    if user.is_client_owner():
        weekly_sales = ImportedSale.objects.filter(connection__client=user.client, business_date__gte=week_start, business_date__lte=today)
        sales_today = ImportedSale.objects.filter(connection__client=user.client, business_date=today)
        paidouts_today = PaidOut.objects.filter(store__client=user.client, created_at__date=today)
        latest_close = DailyClose.objects.filter(store__client=user.client).first()
        return {
            "weekly sales": weekly_sales.aggregate(total=Sum("total_amount"))["total"] or 0,
            "today sales": sales_today.aggregate(total=Sum("total_amount"))["total"] or 0,
            "inventory value": get_inventory_value(user),
            "estimated food cost": sum(item.recipe_cost for item in MenuItem.objects.filter(client=user.client, is_active=True).prefetch_related("recipe_items__ingredient")),
            "paid-outs": paidouts_today.aggregate(total=Sum("amount"))["total"] or 0,
            "inventory variance": "See reports",
            "low stock items": low_stock.count(),
            "daily close status": "Closed" if latest_close and latest_close.business_date == today else "Open",
        }
    latest_count = InventoryCount.objects.filter(store=user.store).first()
    latest_close = DailyClose.objects.filter(store=user.store, business_date=today).first()
    store_sales = ImportedSale.objects.filter(connection__store=user.store)
    return {
        "weekly sales": store_sales.filter(business_date__gte=week_start, business_date__lte=today).aggregate(total=Sum("total_amount"))["total"] or 0,
        "today sales": store_sales.filter(business_date=today).aggregate(total=Sum("total_amount"))["total"] or 0,
        "inventory value": get_inventory_value(user),
        "today purchases": PurchaseReceive.objects.filter(store=user.store, received_at__date=today).aggregate(total=Sum("total"))["total"] or 0,
        "today paid-outs": PaidOut.objects.filter(store=user.store, created_at__date=today).aggregate(total=Sum("amount"))["total"] or 0,
        "latest inventory count": latest_count.business_date if latest_count else "None",
        "daily close status": "Closed" if latest_close else "Open",
        "low stock count": low_stock.count(),
    }


def get_setup_progress(user):
    if not user.is_client_owner():
        return []
    client = user.client
    checks = [
        ("Create at least one store", Store.objects.filter(client=client).exists(), "store_create"),
        ("Create manager logins", User.objects.filter(client=client, role=User.MANAGER).exists(), "manager_create"),
        ("Add vendors", Vendor.objects.filter(client=client).exists(), "vendor_create"),
        ("Add ingredients", Ingredient.objects.filter(client=client).exists(), "ingredient_create"),
        ("Add menu items", MenuItem.objects.filter(client=client).exists(), "menu_item_create"),
        ("Map recipes to ingredients", MenuItem.objects.filter(client=client, recipe_items__isnull=False).distinct().exists(), "recipe_create"),
        ("Connect or create a POS source", POSConnection.objects.filter(client=client).exists(), "pos_connection_create"),
    ]
    return [{"label": label, "done": done, "url": url} for label, done, url in checks]


def get_smart_alerts(user):
    alerts = []
    low_stock = get_low_stock_items(user)[:5]
    for item in low_stock:
        alerts.append({
            "title": f"{item.name} is low",
            "body": f"Current stock is {item.current_quantity} {item.unit}; reorder point is {item.low_stock_level} {item.unit}.",
            "url": "ingredient_list",
        })

    if user.is_client_owner():
        sales = ImportedSale.objects.filter(connection__client=user.client, processed_inventory=False)[:5]
        unmapped = MenuItem.objects.filter(client=user.client, recipe_items__isnull=True, is_active=True).distinct()[:5]
    elif user.is_manager():
        sales = ImportedSale.objects.filter(connection__store=user.store, processed_inventory=False)[:5]
        unmapped = MenuItem.objects.filter(client=user.client, store__in=[user.store, None], recipe_items__isnull=True, is_active=True).distinct()[:5]
    else:
        sales = ImportedSale.objects.filter(processed_inventory=False)[:5]
        unmapped = MenuItem.objects.filter(recipe_items__isnull=True, is_active=True).distinct()[:5]

    if sales:
        alerts.append({
            "title": f"{len(sales)} POS sale(s) need inventory processing",
            "body": "Process imported sales so recipe ingredients deduct automatically.",
            "url": "sale_list",
        })
    for item in unmapped:
        alerts.append({
            "title": f"{item.name} needs a recipe",
            "body": "Map ingredients before processing sales for this item.",
            "url": "recipe_create",
        })
    return alerts[:8]


def get_profit_insights(user):
    if user.is_client_owner():
        items = MenuItem.objects.filter(client=user.client, is_active=True).prefetch_related("recipe_items__ingredient")
    elif user.is_manager():
        items = MenuItem.objects.filter(client=user.client, store__in=[user.store, None], is_active=True).prefetch_related("recipe_items__ingredient")
    else:
        items = MenuItem.objects.filter(is_active=True).prefetch_related("recipe_items__ingredient")
    insights = []
    for item in items:
        if not item.recipe_items.exists():
            continue
        insights.append({
            "name": item.name,
            "price": item.selling_price,
            "cost": item.recipe_cost,
            "profit": item.estimated_profit,
            "food_cost_percent": item.food_cost_percent,
            "status": "Watch" if item.food_cost_percent > 35 else "Healthy",
        })
    return sorted(insights, key=lambda row: row["food_cost_percent"], reverse=True)[:6]


def get_dashboard_context(user):
    context = {
        "stats": _format_dashboard_stats(get_dashboard_stats(user)),
        "setup_progress": get_setup_progress(user),
        "smart_alerts": get_smart_alerts(user),
        "profit_insights": get_profit_insights(user),
        "smart_signals": get_smart_signals(user),
        "dashboard_charts": get_dashboard_charts(user),
    }
    if user.is_super_admin():
        context["platform_insights"] = get_platform_insights()
        context["platform_traffic"] = get_platform_traffic()
    else:
        context["profit_loss"] = get_profit_loss_summary(user)
    return context


def get_dashboard_charts(user):
    if user.is_super_admin():
        return {}
    today = timezone.localdate()
    start = today - timedelta(days=6)
    if user.is_client_owner():
        sales = ImportedSale.objects.filter(connection__client=user.client, business_date__gte=start)
        paidouts = PaidOut.objects.filter(store__client=user.client, business_date__gte=start)
        closes = DailyClose.objects.filter(store__client=user.client, business_date__gte=start)
        ingredients = Ingredient.objects.filter(client=user.client, is_active=True)
    else:
        sales = ImportedSale.objects.filter(connection__store=user.store, business_date__gte=start)
        paidouts = PaidOut.objects.filter(store=user.store, business_date__gte=start)
        closes = DailyClose.objects.filter(store=user.store, business_date__gte=start)
        ingredients = Ingredient.objects.filter(store__in=[user.store, None], client=user.client, is_active=True)

    sales_by_day = {row["business_date"]: row["total"] or 0 for row in sales.values("business_date").annotate(total=Sum("total_amount"))}
    paidouts_by_day = {row["business_date"]: row["total"] or 0 for row in paidouts.values("business_date").annotate(total=Sum("amount"))}
    close_by_day = {row["business_date"]: row["total"] or 0 for row in closes.values("business_date").annotate(total=Sum("short_over"))}
    days = [start + timedelta(days=i) for i in range(7)]

    sales_values = [float(sales_by_day.get(day, 0)) for day in days]
    paidout_values = [float(paidouts_by_day.get(day, 0)) for day in days]
    short_over_values = [float(close_by_day.get(day, 0)) for day in days]
    low_stock = list(ingredients.filter(current_quantity__lte=F("low_stock_level")).order_by("current_quantity")[:6])
    payment_split = _payment_split(user)
    category_split = _category_split(user)

    return {
        "chartjs": {
            "labels": [day.strftime("%a") for day in days],
            "sales": sales_values,
            "paidouts": paidout_values,
            "short_over": short_over_values,
            "payment": [payment_split["cash"], payment_split["card"]],
            "categories": [row["label"] for row in category_split],
            "category_values": [row["value"] for row in category_split],
        },
        "sales": _bar_chart("Sales", days, sales_values, prefix="$"),
        "paidouts": _bar_chart("Paid-Outs", days, paidout_values, prefix="$"),
        "short_over": _bar_chart("Short / Over", days, short_over_values, prefix="$", allow_negative=True),
        "weekly_sales_trend": _weekly_sales_trend(user),
        "payment_split": payment_split,
        "category_split": category_split,
        "low_stock": [
            {
                "label": item.name,
                "value": float(item.current_quantity),
                "target": float(item.low_stock_level or 0),
                "unit": item.inventory_unit,
                "percent": _percent(float(item.current_quantity), float(item.low_stock_level or 1)),
            }
            for item in low_stock
        ],
    }


def _format_dashboard_stats(stats):
    money_keys = {"platform sales", "inventory handled", "weekly sales", "today sales", "inventory value", "estimated food cost", "paid-outs", "today purchases", "today paid-outs", "net profit"}
    formatted = {}
    for label, value in stats.items():
        if label in money_keys:
            try:
                formatted[label] = f"${float(value):,.2f}"
            except (TypeError, ValueError):
                formatted[label] = value
        else:
            formatted[label] = value
    return formatted


def get_profit_loss_summary(user, start_date=None, end_date=None, store=None):
    today = timezone.localdate()
    if start_date is None:
        start_date = today.replace(day=1)
    if end_date is None:
        end_date = today

    if user.is_super_admin():
        stores = Store.objects.filter(is_active=True)
    elif user.is_client_owner():
        stores = Store.objects.filter(client=user.client, is_active=True)
    else:
        stores = Store.objects.filter(pk=user.store_id)
    if store:
        stores = stores.filter(pk=store.pk)

    sales = ImportedSale.objects.filter(connection__store__in=stores, business_date__gte=start_date, business_date__lte=end_date)
    paidouts = PaidOut.objects.filter(store__in=stores, business_date__gte=start_date, business_date__lte=end_date)
    purchases = PurchaseReceive.objects.filter(store__in=stores, invoice_date__gte=start_date, invoice_date__lte=end_date)
    closes = DailyClose.objects.filter(store__in=stores, business_date__gte=start_date, business_date__lte=end_date)

    zero = Decimal("0")
    revenue = sales.aggregate(total=Sum("total_amount"))["total"] or zero
    cash_sales = sales.aggregate(total=Sum("cash_amount"))["total"] or zero
    card_sales = sales.aggregate(total=Sum("card_amount"))["total"] or zero
    tax_collected = sales.aggregate(total=Sum("tax_amount"))["total"] or zero
    tips_collected = sales.aggregate(total=Sum("tip_amount"))["total"] or zero
    discounts = sales.aggregate(total=Sum("discount_amount"))["total"] or zero
    net_sales = revenue - tax_collected - tips_collected
    paidout_total = paidouts.aggregate(total=Sum("amount"))["total"] or zero
    inventory_paidouts = paidouts.filter(category__in=INVENTORY_PAIDOUT_CATEGORIES).aggregate(total=Sum("amount"))["total"] or zero
    operating_paidouts = paidouts.filter(category__in=OPERATING_PAIDOUT_CATEGORIES).aggregate(total=Sum("amount"))["total"] or zero
    uncategorized_paidouts = paidout_total - inventory_paidouts - operating_paidouts
    purchase_total = purchases.aggregate(total=Sum("total"))["total"] or zero
    cash_variance = closes.aggregate(total=Sum("short_over"))["total"] or zero
    theoretical_cogs = get_theoretical_cogs(sales)
    actual_cogs = get_actual_pos_cogs(sales)
    food_cogs = actual_cogs or theoretical_cogs
    gross_profit = net_sales - food_cogs
    operating_expenses = operating_paidouts + uncategorized_paidouts
    net_profit = gross_profit - operating_expenses + cash_variance
    inventory_cash_outflow = purchase_total + inventory_paidouts
    cash_flow_after_inventory = cash_sales + card_sales - inventory_cash_outflow - operating_expenses + cash_variance
    food_cost_percent = (food_cogs / net_sales * 100) if net_sales else 0
    gross_margin = (gross_profit / net_sales * 100) if net_sales else 0
    margin = (net_profit / net_sales * 100) if net_sales else 0

    return {
        "period": f"{start_date:%b %d} - {end_date:%b %d}",
        "revenue": revenue,
        "net_sales": net_sales,
        "cash_sales": cash_sales,
        "card_sales": card_sales,
        "tax_collected": tax_collected,
        "tips_collected": tips_collected,
        "discounts": discounts,
        "theoretical_cogs": theoretical_cogs,
        "actual_cogs": actual_cogs,
        "food_cogs": food_cogs,
        "gross_profit": gross_profit,
        "paidouts": paidout_total,
        "inventory_paidouts": inventory_paidouts,
        "operating_paidouts": operating_paidouts,
        "uncategorized_paidouts": uncategorized_paidouts,
        "operating_expenses": operating_expenses,
        "purchase_spend": purchase_total,
        "inventory_cash_outflow": inventory_cash_outflow,
        "cash_variance": cash_variance,
        "net_profit": net_profit,
        "cash_flow_after_inventory": cash_flow_after_inventory,
        "food_cost_percent": food_cost_percent,
        "gross_margin": gross_margin,
        "margin": margin,
        "processed_sales": sales.filter(processed_inventory=True).count(),
        "unprocessed_sales": sales.filter(processed_inventory=False).count(),
    }


def get_theoretical_cogs(sales):
    recipe_cost_expr = ExpressionWrapper(
        F("recipe_items__quantity_used") * F("recipe_items__ingredient__average_cost"),
        output_field=DecimalField(max_digits=14, decimal_places=4),
    )
    menu_costs = {
        row["id"]: row["recipe_cost"] or Decimal("0")
        for row in MenuItem.objects.filter(sale_items__sale__in=sales)
        .values("id")
        .annotate(recipe_cost=Sum(recipe_cost_expr))
    }
    total = Decimal("0")
    for row in ImportedSaleItem.objects.filter(sale__in=sales, mapped_menu_item_id__isnull=False).values("mapped_menu_item_id").annotate(quantity=Sum("quantity")):
        total += (row["quantity"] or Decimal("0")) * menu_costs.get(row["mapped_menu_item_id"], Decimal("0"))
    return total


def get_actual_pos_cogs(sales):
    movement_cost_expr = ExpressionWrapper(
        F("quantity") * F("ingredient__average_cost"),
        output_field=DecimalField(max_digits=14, decimal_places=4),
    )
    return StockMovement.objects.filter(
        movement_type=StockMovement.POS_DEDUCTION,
        source_sale_id__in=sales.values("external_order_id"),
    ).aggregate(total=Sum(movement_cost_expr))["total"] or Decimal("0")


def get_monthly_report_summary(user, year=None, month=None, store=None):
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month
    start_date = date(year, month, 1)
    end_date = start_date.replace(day=monthrange(year, month)[1])

    if user.is_super_admin():
        stores = Store.objects.filter(is_active=True)
    elif user.is_client_owner():
        stores = Store.objects.filter(client=user.client, is_active=True)
    else:
        stores = Store.objects.filter(pk=user.store_id)
    if store:
        stores = stores.filter(pk=store.pk)

    sales = ImportedSale.objects.filter(connection__store__in=stores, business_date__gte=start_date, business_date__lte=end_date)
    paidouts = PaidOut.objects.filter(store__in=stores, business_date__gte=start_date, business_date__lte=end_date)
    purchases = PurchaseReceive.objects.filter(store__in=stores, invoice_date__gte=start_date, invoice_date__lte=end_date)
    closes = DailyClose.objects.filter(store__in=stores, business_date__gte=start_date, business_date__lte=end_date)
    ingredients = Ingredient.objects.filter(store__in=stores)
    if not user.is_super_admin() and getattr(user, "client_id", None):
        ingredients = ingredients.filter(client=user.client)

    value_expr = ExpressionWrapper(F("current_quantity") * F("average_cost"), output_field=DecimalField(max_digits=14, decimal_places=2))
    profit_loss = get_profit_loss_summary(user, start_date=start_date, end_date=end_date, store=store) if not user.is_super_admin() else None
    sales_by_day = OrderedDict()
    for day in range(1, end_date.day + 1):
        business_date = start_date.replace(day=day)
        sales_by_day[business_date] = Decimal("0")
    for row in sales.values("business_date").annotate(total=Sum("total_amount")).order_by("business_date"):
        sales_by_day[row["business_date"]] = row["total"] or Decimal("0")

    return {
        "label": start_date.strftime("%B %Y"),
        "start_date": start_date,
        "end_date": end_date,
        "sales": sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0"),
        "orders": sales.count(),
        "cash_sales": sales.aggregate(total=Sum("cash_amount"))["total"] or Decimal("0"),
        "card_sales": sales.aggregate(total=Sum("card_amount"))["total"] or Decimal("0"),
        "paidouts": paidouts.aggregate(total=Sum("amount"))["total"] or Decimal("0"),
        "purchases": purchases.aggregate(total=Sum("total"))["total"] or Decimal("0"),
        "short_over": closes.aggregate(total=Sum("short_over"))["total"] or Decimal("0"),
        "inventory_value": ingredients.aggregate(total=Sum(value_expr))["total"] or Decimal("0"),
        "inventory_movements": StockMovement.objects.filter(ingredient__in=ingredients, created_at__date__gte=start_date, created_at__date__lte=end_date).count(),
        "low_stock_count": ingredients.filter(current_quantity__lte=F("low_stock_level")).count(),
        "daily_sales": [{"date": business_date, "total": total} for business_date, total in sales_by_day.items() if total],
        "paidouts_by_category": paidouts.values("category").annotate(total=Sum("amount")).order_by("category"),
        "profit_loss": profit_loss,
    }


def _month_scope(user):
    today = timezone.localdate()
    start = today.replace(day=1)
    end = today.replace(day=monthrange(today.year, today.month)[1])
    if user.is_client_owner():
        sales = ImportedSale.objects.filter(connection__client=user.client, business_date__gte=start, business_date__lte=end)
        paidouts = PaidOut.objects.filter(store__client=user.client, business_date__gte=start, business_date__lte=end)
        purchases = PurchaseReceive.objects.filter(store__client=user.client, invoice_date__gte=start, invoice_date__lte=end)
    else:
        sales = ImportedSale.objects.filter(connection__store=user.store, business_date__gte=start, business_date__lte=end)
        paidouts = PaidOut.objects.filter(store=user.store, business_date__gte=start, business_date__lte=end)
        purchases = PurchaseReceive.objects.filter(store=user.store, invoice_date__gte=start, invoice_date__lte=end)
    return start, today, sales, paidouts, purchases


def _weekly_sales_trend(user):
    today = timezone.localdate()
    start = today - timedelta(days=6)
    if user.is_client_owner():
        sales = ImportedSale.objects.filter(connection__client=user.client, business_date__gte=start, business_date__lte=today)
    else:
        sales = ImportedSale.objects.filter(connection__store=user.store, business_date__gte=start, business_date__lte=today)
    totals = {row["business_date"]: float(row["total"] or 0) for row in sales.values("business_date").annotate(total=Sum("total_amount"))}
    days = [start + timedelta(days=i) for i in range(7)]
    values = [totals.get(day, 0) for day in days]
    max_value = max(values + [1])
    points = []
    width = 640
    height = 220
    for index, value in enumerate(values):
        x = 0 if len(values) == 1 else (index / (len(values) - 1)) * width
        y = height - ((value / max_value) * (height - 20))
        points.append({"x": round(x, 2), "y": round(y, 2), "value": value, "label": days[index].strftime("%b %d")})
    line_points = " ".join(f"{point['x']},{point['y']}" for point in points)
    area_points = f"0,{height} {line_points} {width},{height}" if points else ""
    return {"points": points, "line_points": line_points, "area_points": area_points, "max": max_value}


def _payment_split(user):
    _start, _today, sales, _paidouts, _purchases = _month_scope(user)
    cash = float(sales.aggregate(total=Sum("cash_amount"))["total"] or 0)
    card = float(sales.aggregate(total=Sum("card_amount"))["total"] or 0)
    total = cash + card
    cash_percent = round((cash / total) * 100, 1) if total else 0
    card_percent = round(100 - cash_percent, 1) if total else 0
    return {
        "cash": cash,
        "card": card,
        "cash_percent": cash_percent,
        "card_percent": card_percent,
        "gradient": f"conic-gradient(#38bdf8 0 {cash_percent}%, #fb7185 {cash_percent}% 100%)" if total else "conic-gradient(#e5e7eb 0 100%)",
    }


def _category_split(user):
    _start, _today, _sales, paidouts, purchases = _month_scope(user)
    inventory_total = float(purchases.aggregate(total=Sum("total"))["total"] or 0)
    expense_total = float(paidouts.aggregate(total=Sum("amount"))["total"] or 0)
    max_value = max(inventory_total, expense_total, 1)
    return [
        {"label": "Inventory", "value": inventory_total, "height": max(6, int((inventory_total / max_value) * 100))},
        {"label": "Expense", "value": expense_total, "height": max(6, int((expense_total / max_value) * 100))},
    ]


def _bar_chart(title, days, values, prefix="", allow_negative=False):
    max_value = max([abs(value) for value in values] + [1]) if allow_negative else max(values + [1])
    return {
        "title": title,
        "bars": [
            {
                "label": day.strftime("%a"),
                "value": value,
                "display": f"{prefix}{value:,.2f}" if prefix else f"{value:,.0f}",
                "height": max(6, int((abs(value) / max_value) * 100)),
                "negative": value < 0,
            }
            for day, value in zip(days, values)
        ],
    }


def _percent(value, target):
    if target <= 0:
        return 100
    return min(100, max(4, int((value / target) * 100)))


def get_platform_traffic(days=7):
    since = timezone.now() - timedelta(days=days)
    labels = [f"{hour:02d}:00" for hour in range(24)]
    counts = [0 for _ in range(24)]
    sources = [
        ImportedSale.objects.filter(imported_at__gte=since).annotate(hour=ExtractHour("imported_at")).values("hour").annotate(total=Count("id")),
        PaidOut.objects.filter(created_at__gte=since).annotate(hour=ExtractHour("created_at")).values("hour").annotate(total=Count("id")),
        PurchaseReceive.objects.filter(received_at__gte=since).annotate(hour=ExtractHour("received_at")).values("hour").annotate(total=Count("id")),
        StockMovement.objects.filter(created_at__gte=since).annotate(hour=ExtractHour("created_at")).values("hour").annotate(total=Count("id")),
    ]
    for source in sources:
        for row in source:
            if row["hour"] is not None:
                counts[int(row["hour"])] += row["total"]
    peak_value = max(counts) if counts else 0
    peak_hour = labels[counts.index(peak_value)] if peak_value else "No activity"
    return {
        "labels": labels,
        "counts": counts,
        "peak_hour": peak_hour,
        "peak_value": peak_value,
        "window": f"Last {days} days",
    }


def get_platform_insights():
    value_expr = ExpressionWrapper(F("current_quantity") * F("average_cost"), output_field=DecimalField(max_digits=14, decimal_places=2))
    client_rows = []
    for client in Client.objects.order_by("name"):
        sales = ImportedSale.objects.filter(connection__client=client)
        ingredients = Ingredient.objects.filter(client=client)
        client_rows.append({
            "name": client.name,
            "status": client.get_status_display(),
            "sales": sales.aggregate(total=Sum("total_amount"))["total"] or 0,
            "sales_count": sales.count(),
            "inventory_value": ingredients.aggregate(total=Sum(value_expr))["total"] or 0,
            "inventory_items": ingredients.count(),
            "inventory_movements": StockMovement.objects.filter(ingredient__client=client).count(),
        })
    return {
        "client_rows": client_rows,
        "active_hours": get_platform_traffic(),
    }


def get_report_summary(user):
    paidouts = PaidOut.objects.all()
    closes = DailyClose.objects.all()
    ingredients = Ingredient.objects.all()
    sales = ImportedSale.objects.all()
    movements = StockMovement.objects.select_related("ingredient")
    if user.is_client_owner():
        paidouts = paidouts.filter(store__client=user.client)
        closes = closes.filter(store__client=user.client)
        ingredients = ingredients.filter(client=user.client)
        sales = sales.filter(connection__client=user.client)
        movements = movements.filter(ingredient__client=user.client)
    elif user.is_manager():
        paidouts = paidouts.filter(store=user.store)
        closes = closes.filter(store=user.store)
        ingredients = ingredients.filter(store=user.store)
        sales = sales.filter(connection__store=user.store)
        movements = movements.filter(ingredient__store=user.store)
    return {
        "total_paidouts": paidouts.aggregate(total=Sum("amount"))["total"] or 0,
        "paidouts_by_category": paidouts.values("category").annotate(total=Sum("amount")).order_by("category"),
        "paidouts_by_store": paidouts.values("store__name").annotate(total=Sum("amount")).order_by("store__name"),
        "daily_closes": closes[:20],
        "short_over": closes.aggregate(total=Sum("short_over"))["total"] or 0,
        "cash_sales": sales.aggregate(total=Sum("cash_amount"))["total"] or 0,
        "card_sales": sales.aggregate(total=Sum("card_amount"))["total"] or 0,
        "low_stock": ingredients.filter(current_quantity__lte=F("low_stock_level")),
        "inventory_value": sum(i.value_estimate for i in ingredients),
        "recent_movements": movements[:10],
        "unprocessed_sales": sales.filter(processed_inventory=False).count(),
        "processed_sales": sales.filter(processed_inventory=True).count(),
    }
