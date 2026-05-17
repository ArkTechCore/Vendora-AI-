from django.db.models import Sum

from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale


def calculate_daily_close_totals(store, business_date):
    sales = ImportedSale.objects.filter(connection__store=store, business_date=business_date).aggregate(
        cash=Sum("cash_amount"),
        card=Sum("card_amount"),
    )
    paidouts = PaidOut.objects.filter(
        store=store,
        approved=True,
        payment_source="cash",
        business_date=business_date,
    ).aggregate(total=Sum("amount"))
    return {
        "cash_sales": sales["cash"] or 0,
        "card_sales": sales["card"] or 0,
        "cash_paidouts": paidouts["total"] or 0,
    }
