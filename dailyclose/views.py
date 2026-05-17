from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.access import permission_required, role_required
from accounts.services import log_audit
from reports.notifications import send_daily_close_notification
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale
from .forms import DailyCloseForm
from .models import DailyClose

def scoped_closes(user):
    if user.is_super_admin():
        return DailyClose.objects.select_related("store", "closed_by")
    if user.is_client_owner():
        return DailyClose.objects.filter(store__client=user.client)
    return DailyClose.objects.filter(store=user.store)


@role_required("client_owner", "manager")
@permission_required("can_close_day")
def close_list(request):
    return render(request, "dailyclose/list.html", {"title": "Daily Close", "objects": scoped_closes(request.user)})


@role_required("client_owner", "manager")
@permission_required("can_close_day")
def close_form(request):
    form = DailyCloseForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        close = form.save(commit=False)
        if request.user.is_manager():
            close.store = request.user.store
        close.closed_by = request.user
        close.created_by = request.user
        close.save()
        log_audit(request.user, "daily_close_submitted", f"Daily close submitted for {close.store.name} on {close.business_date}.", close)
        send_daily_close_notification(close)
        messages.success(request, "Daily close saved and locked.")
        return redirect("daily_close_list")
    return render(request, "form.html", {"title": "Daily Close", "form": form})


@role_required("client_owner", "manager")
@permission_required("can_close_day")
def close_receipt(request, pk):
    close = get_object_or_404(scoped_closes(request.user), pk=pk)
    sales = ImportedSale.objects.filter(connection__store=close.store, business_date=close.business_date).prefetch_related("items")
    paidouts = PaidOut.objects.filter(store=close.store, business_date=close.business_date, payment_source="cash")
    return render(request, "dailyclose/receipt.html", {"close": close, "sales": sales, "paidouts": paidouts})
