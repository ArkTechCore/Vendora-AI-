from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.access import role_required
from .forms import StoreForm
from .models import Store

def _stores_for(user):
    if user.is_super_admin():
        return Store.objects.select_related("client")
    if user.is_client_owner():
        return Store.objects.filter(client=user.client)
    return Store.objects.filter(pk=user.store_id)


@role_required("super_admin")
def store_list(request):
    return render(request, "list.html", {"title": "Stores", "create_url": "store_create", "objects": _stores_for(request.user), "columns": ["name", "client", "code", "address", "is_active"]})


@role_required("super_admin")
def store_form(request, pk=None):
    store = get_object_or_404(_stores_for(request.user), pk=pk) if pk else None
    form = StoreForm(request.POST or None, instance=store, user=request.user)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.save()
        messages.success(request, "Store saved.")
        return redirect("store_list")
    return render(request, "form.html", {"title": "Store", "form": form})
