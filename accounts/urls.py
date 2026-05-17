from django.urls import path
from django.contrib.auth import views as auth_views

from .views import (
    VendoraLoginView,
    VendoraLogoutView,
    VendoraPasswordResetView,
    audit_log_list,
    client_owner_create,
    manager_create,
    manager_edit,
    manager_list,
    message_create,
    message_detail,
    message_list,
)

urlpatterns = [
    path("login/", VendoraLoginView.as_view(), name="login"),
    path("logout/", VendoraLogoutView.as_view(), name="logout"),
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(template_name="accounts/password_change.html"),
        name="password_change",
    ),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="accounts/password_change_done.html"),
        name="password_change_done",
    ),
    path(
        "password/reset/",
        VendoraPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password/reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("client-owner/new/", client_owner_create, name="client_owner_create"),
    path("managers/", manager_list, name="manager_list"),
    path("manager/new/", manager_create, name="manager_create"),
    path("managers/<int:pk>/edit/", manager_edit, name="manager_edit"),
    path("audit-logs/", audit_log_list, name="audit_log_list"),
    path("messages/", message_list, name="message_list"),
    path("messages/new/", message_create, name="message_create"),
    path("messages/<int:pk>/", message_detail, name="message_detail"),
]
