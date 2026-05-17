from django.contrib import messages
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render

from accounts.access import role_required
from accounts.services import log_audit
from .filters import ClientFilter
from .forms import ClientEditForm, ClientOnboardingForm
from .models import Client
from .tables import ClientTable

@role_required("super_admin")
def client_list(request):
    clients = Client.objects.prefetch_related("users").all()
    filterset = ClientFilter(request.GET, queryset=clients)
    table = ClientTable(filterset.qs)
    table.paginate(page=request.GET.get("page", 1), per_page=25)
    return render(request, "clients/list.html", {"title": "Clients", "filter": filterset, "table": table})


@role_required("super_admin")
def client_form(request, pk=None):
    client = get_object_or_404(Client, pk=pk) if pk else None
    form_class = ClientEditForm if client else ClientOnboardingForm
    form = form_class(request.POST or None, instance=client) if client else form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if client:
            form.save()
            messages.success(request, "Client saved.")
        else:
            new_client, owner = form.save()
            log_audit(request.user, "client_created", f"Created client {new_client.name} and owner login {owner.username}.", new_client, safe_for_platform=True)
            messages.success(request, f"Client {new_client.name} and owner login {owner.username} created.")
        return redirect("client_list")
    title = "Edit Client" if client else "Create Client and Owner Login"
    template = "clients/form.html" if client else "clients/onboarding_form.html"
    return render(request, template, {"title": title, "form": form, "client": client})


@role_required("super_admin")
@require_POST
def client_status(request, pk, status):
    client = get_object_or_404(Client, pk=pk)
    if status not in dict(Client.STATUS_CHOICES):
        messages.error(request, "Invalid client status.")
    else:
        client.status = status
        client.save(update_fields=["status"])
        log_audit(request.user, f"client_{status}", f"{client.name} set to {client.get_status_display()}.", client, safe_for_platform=True)
        messages.success(request, f"{client.name} is now {client.get_status_display()}.")
    return redirect("client_list")
