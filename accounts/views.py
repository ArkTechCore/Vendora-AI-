from django.contrib import messages
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView
from django.db import models
from django.middleware.csrf import rotate_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from .access import role_required
from .forms import ClientMessageForm, ClientOwnerCreationForm, ManagerCreationForm, ManagerEditForm, VendoraLoginForm
from .models import AuditLog, ClientMessage, ClientMessageRead, User


@method_decorator([never_cache, ensure_csrf_cookie], name="dispatch")
class VendoraLoginView(LoginView):
    authentication_form = VendoraLoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return "/"

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        AuditLog.objects.create(
            user=user,
            client=user.client if user.client_id else None,
            store=user.store if user.store_id else None,
            action="login",
            model_name="User",
            object_id=str(user.id),
            message=f"{user} logged in at {timezone.localtime():%Y-%m-%d %H:%M}.",
            safe_for_platform=user.is_super_admin(),
        )
        return response


@method_decorator(never_cache, name="dispatch")
class VendoraLogoutView(LogoutView):
    def post(self, request, *args, **kwargs):
        logout(request)
        rotate_token(request)
        response = redirect(self.get_success_url())
        response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/", samesite=settings.CSRF_COOKIE_SAMESITE)
        return response


class VendoraPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"

    def form_valid(self, form):
        if settings.DEBUG:
            links = []
            for user in form.get_users(form.cleaned_data["email"]):
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                path = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
                links.append(self.request.build_absolute_uri(path))
            self.request.session["dev_password_reset_links"] = links
        return super().form_valid(form)


@role_required("client_owner")
def manager_create(request):
    form = ManagerCreationForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        manager = form.save()
        messages.success(request, f"Manager {manager} created.")
        return redirect("manager_list")
    return render(request, "form.html", {"title": "Create Manager", "form": form})


@role_required("client_owner")
def manager_list(request):
    managers = User.objects.filter(client=request.user.client, role=User.MANAGER).select_related("store").order_by("store__name", "username")
    return render(request, "accounts/manager_list.html", {"managers": managers})


@role_required("client_owner")
def manager_edit(request, pk):
    manager = get_object_or_404(User, pk=pk, client=request.user.client, role=User.MANAGER)
    form = ManagerEditForm(request.POST or None, instance=manager, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Manager {manager} permissions updated.")
        return redirect("manager_list")
    return render(request, "form.html", {"title": f"Edit Manager: {manager}", "form": form})


@role_required("super_admin")
def client_owner_create(request):
    form = ClientOwnerCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        owner = form.save()
        messages.success(request, f"Client owner {owner} created.")
        return redirect("client_owner_create")
    return render(request, "form.html", {"title": "Create Client Owner", "form": form})


@role_required("client_owner")
def audit_log_list(request):
    logs = AuditLog.objects.filter(client=request.user.client).select_related("user", "store")[:100]
    return render(request, "accounts/audit_logs.html", {"logs": logs})


def visible_messages(user):
    if user.is_super_admin():
        return ClientMessage.objects.select_related("sender", "client")
    return ClientMessage.objects.filter(
        models.Q(audience=ClientMessage.ALL_CLIENTS)
        | models.Q(audience=ClientMessage.CLIENT, client=user.client)
        | models.Q(audience=ClientMessage.PLATFORM, client=user.client)
    ).select_related("sender", "client")


@role_required("super_admin", "client_owner", "manager")
def message_list(request):
    messages_qs = visible_messages(request.user).prefetch_related("reads")[:100]
    read_ids = set(
        ClientMessageRead.objects.filter(user=request.user, message__in=messages_qs).values_list("message_id", flat=True)
    )
    return render(request, "accounts/message_list.html", {"client_messages": messages_qs, "read_ids": read_ids})


@role_required("super_admin", "client_owner", "manager")
def message_detail(request, pk):
    message = get_object_or_404(visible_messages(request.user), pk=pk)
    if message.sender_id != request.user.id:
        ClientMessageRead.objects.get_or_create(message=message, user=request.user)
    return render(request, "accounts/message_detail.html", {"client_message": message})


@role_required("super_admin", "client_owner", "manager")
def message_create(request):
    form = ClientMessageForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        recipient = form.cleaned_data["recipient"]
        if request.user.is_super_admin():
            audience = ClientMessage.ALL_CLIENTS if recipient == "all" else ClientMessage.CLIENT
            client = None if recipient == "all" else form.cleaned_data["client"]
        else:
            audience = ClientMessage.PLATFORM
            client = request.user.client
        message = ClientMessage.objects.create(
            sender=request.user,
            client=client,
            audience=audience,
            subject=form.cleaned_data["subject"],
            body=form.cleaned_data["body"],
        )
        ClientMessageRead.objects.get_or_create(message=message, user=request.user)
        messages.success(request, "Message sent.")
        return redirect("message_list")
    return render(request, "accounts/message_form.html", {"form": form})
