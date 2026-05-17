from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from accounts.access import permission_required, role_required
from accounts.services import log_audit
from .forms import PaidOutForm
from .models import PaidOut

def scoped_paidouts(user):
    if user.is_super_admin():
        return PaidOut.objects.select_related("store", "created_by")
    if user.is_client_owner():
        return PaidOut.objects.filter(store__client=user.client)
    return PaidOut.objects.filter(store=user.store)


@role_required("client_owner", "manager")
@permission_required("can_manage_paidouts")
def paidout_list(request):
    qs = scoped_paidouts(request.user).select_related("store", "created_by").order_by("-business_date", "-created_at")
    paginator = Paginator(qs, 100)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "paidouts/list.html", {"title": "Paid-Outs", "objects": page_obj, "page_obj": page_obj})


@role_required("client_owner", "manager")
@permission_required("can_manage_paidouts")
def paidout_form(request):
    form = PaidOutForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        paidout = form.save(commit=False)
        if request.user.is_manager():
            paidout.store = request.user.store
        paidout.created_by = request.user
        paidout.save()
        log_audit(request.user, "paidout_created", f"Paid-out created for {paidout.amount}.", paidout)
        messages.success(request, "Paid-out saved and locked.")
        return redirect("paidout_list")
    return render(request, "form.html", {"title": "Paid-Out", "form": form})
