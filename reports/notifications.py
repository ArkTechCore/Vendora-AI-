from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from accounts.models import User
from clients.models import Client
from dailyclose.models import DailyClose
from inventory.models import Ingredient, PurchaseReceive, StockMovement
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale
from stores.models import Store


def money(value):
    try:
        return f"${Decimal(str(value or 0)):,.2f}"
    except Exception:
        return str(value)


def client_owner_emails(client):
    return list(
        User.objects.filter(client=client, role=User.CLIENT_OWNER, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )


def super_admin_emails():
    configured = getattr(settings, "PLATFORM_NOTIFICATION_EMAILS", [])
    if configured:
        return configured
    return list(User.objects.filter(is_superuser=True, is_active=True).exclude(email="").values_list("email", flat=True))


def send_daily_close_notification(close):
    recipients = client_owner_emails(close.store.client)
    if not recipients:
        return 0
    subject = f"VendoraOps Daily Close - {close.store.name} - {close.business_date:%b %d, %Y}"
    body = "\n".join([
        f"Daily close submitted for {close.store.name}.",
        "",
        f"Business date: {close.business_date:%B %d, %Y}",
        f"Opening cash: {money(close.opening_cash)}",
        f"Cash sales: {money(close.cash_sales)}",
        f"Card sales: {money(close.card_sales)}",
        f"Cash paid-outs: {money(close.cash_paidouts)}",
        f"Expected cash: {money(close.expected_cash)}",
        f"Counted cash: {money(close.counted_cash)}",
        f"Short / over: {money(close.short_over)}",
        "",
        "Generated automatically by VendoraOps.",
    ])
    return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)


def send_client_period_report(client, start_date, end_date, label):
    recipients = client_owner_emails(client)
    if not recipients:
        return 0
    stores = Store.objects.filter(client=client, is_active=True)
    sales = ImportedSale.objects.filter(connection__store__in=stores, business_date__gte=start_date, business_date__lte=end_date)
    paidouts = PaidOut.objects.filter(store__in=stores, business_date__gte=start_date, business_date__lte=end_date)
    purchases = PurchaseReceive.objects.filter(store__in=stores, invoice_date__gte=start_date, invoice_date__lte=end_date)
    closes = DailyClose.objects.filter(store__in=stores, business_date__gte=start_date, business_date__lte=end_date)
    value_expr = ExpressionWrapper(F("current_quantity") * F("average_cost"), output_field=DecimalField(max_digits=14, decimal_places=2))
    ingredients = Ingredient.objects.filter(client=client)
    body = "\n".join([
        f"{label} summary for {client.name}",
        f"Period: {start_date:%b %d, %Y} to {end_date:%b %d, %Y}",
        "",
        f"Sales: {money(sales.aggregate(total=Sum('total_amount'))['total'])}",
        f"Orders: {sales.count():,}",
        f"Purchases: {money(purchases.aggregate(total=Sum('total'))['total'])}",
        f"Paid-outs: {money(paidouts.aggregate(total=Sum('amount'))['total'])}",
        f"Short / over: {money(closes.aggregate(total=Sum('short_over'))['total'])}",
        f"Inventory value handled: {money(ingredients.aggregate(total=Sum(value_expr))['total'])}",
        f"Inventory movements: {StockMovement.objects.filter(ingredient__client=client, created_at__date__gte=start_date, created_at__date__lte=end_date).count():,}",
        "",
        "Generated automatically by VendoraOps.",
    ])
    subject = f"VendoraOps {label} Report - {client.name}"
    return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)


def send_platform_period_report(start_date, end_date, label):
    recipients = super_admin_emails()
    if not recipients:
        return 0
    sales = ImportedSale.objects.filter(business_date__gte=start_date, business_date__lte=end_date)
    value_expr = ExpressionWrapper(F("current_quantity") * F("average_cost"), output_field=DecimalField(max_digits=14, decimal_places=2))
    body = "\n".join([
        f"VendoraOps platform-safe {label.lower()} summary",
        f"Period: {start_date:%b %d, %Y} to {end_date:%b %d, %Y}",
        "",
        f"Platform sales handled: {money(sales.aggregate(total=Sum('total_amount'))['total'])}",
        f"Orders handled: {sales.count():,}",
        f"Active clients: {Client.objects.filter(status=Client.ACTIVE).count():,}",
        f"Total stores: {Store.objects.count():,}",
        f"Inventory value handled: {money(Ingredient.objects.aggregate(total=Sum(value_expr))['total'])}",
        f"Inventory items handled: {Ingredient.objects.count():,}",
        f"Inventory movements handled: {StockMovement.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date).count():,}",
        "",
        "No paid-out notes, receipts, vendor pricing, store-level rows, or restaurant cash detail are included.",
    ])
    return send_mail(f"VendoraOps Platform {label} Report", body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)


def period_dates(period, reference_date=None):
    reference_date = reference_date or timezone.localdate()
    if period == "weekly":
        return reference_date - timedelta(days=6), reference_date, "Weekly"
    if period == "monthly":
        first_this_month = reference_date.replace(day=1)
        last_previous_month = first_this_month - timedelta(days=1)
        start = date(last_previous_month.year, last_previous_month.month, 1)
        end = date(last_previous_month.year, last_previous_month.month, monthrange(last_previous_month.year, last_previous_month.month)[1])
        return start, end, "Month-End"
    raise ValueError("period must be weekly or monthly")
