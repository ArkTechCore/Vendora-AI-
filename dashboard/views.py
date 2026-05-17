from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .services import get_dashboard_context

@login_required
def dashboard(request):
    user = request.user
    context = get_dashboard_context(user)
    if user.is_super_admin():
        template = "dashboard/super_admin_dashboard.html"
    elif user.is_client_owner():
        template = "dashboard/client_dashboard.html"
    else:
        template = "dashboard/manager_dashboard.html"
    return render(request, template, context)


@login_required
def settings_hub(request):
    if request.user.is_manager():
        return redirect("dashboard")
    template = "dashboard/super_admin_settings.html" if request.user.is_super_admin() else "dashboard/client_settings.html"
    context = {}
    if request.user.is_client_owner():
        context["stores"] = request.user.client.stores.order_by("name")
        context["client"] = request.user.client
    else:
        context = get_dashboard_context(request.user)
    return render(request, template, context)
