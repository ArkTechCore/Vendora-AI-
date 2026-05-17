from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    SUPER_ADMIN = 'super_admin'
    CLIENT_OWNER = 'client_owner'
    MANAGER = 'manager'
    ROLE_CHOICES = [
        (SUPER_ADMIN, 'Super Admin'),
        (CLIENT_OWNER, 'Client Owner'),
        (MANAGER, 'Manager'),
    ]

    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=MANAGER)
    client = models.ForeignKey('clients.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    store = models.ForeignKey('stores.Store', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    can_manage_inventory = models.BooleanField(default=True)
    can_manage_paidouts = models.BooleanField(default=True)
    can_close_day = models.BooleanField(default=True)
    can_view_reports = models.BooleanField(default=True)
    can_manage_pos = models.BooleanField(default=False)

    def is_super_admin(self):
        return self.role == self.SUPER_ADMIN or self.is_superuser

    def is_client_owner(self):
        return self.role == self.CLIENT_OWNER

    def is_manager(self):
        return self.role == self.MANAGER

    def has_manager_permission(self, permission):
        if self.is_super_admin() or self.is_client_owner():
            return True
        return bool(getattr(self, permission, False))

    def __str__(self):
        return self.get_full_name() or self.username


class AuditLog(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs')
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=80)
    model_name = models.CharField(max_length=120, blank=True)
    object_id = models.CharField(max_length=80, blank=True)
    message = models.TextField(blank=True)
    safe_for_platform = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.created_at:%Y-%m-%d %H:%M}"


class ClientMessage(models.Model):
    PLATFORM = "platform"
    CLIENT = "client"
    ALL_CLIENTS = "all_clients"
    AUDIENCE_CHOICES = [
        (PLATFORM, "Platform support"),
        (CLIENT, "One client"),
        (ALL_CLIENTS, "All clients"),
    ]

    sender = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="sent_client_messages")
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, null=True, blank=True, related_name="messages")
    audience = models.CharField(max_length=24, choices=AUDIENCE_CHOICES)
    subject = models.CharField(max_length=160)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class ClientMessageRead(models.Model):
    message = models.ForeignKey(ClientMessage, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="read_client_messages")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user")
