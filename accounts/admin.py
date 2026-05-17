from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, ClientMessage, ClientMessageRead, User

@admin.register(User)
class VendoraUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("VendoraOps Access", {"fields": ("role", "client", "store")}),)
    list_display = ("username", "email", "role", "client", "store", "is_staff")
    list_filter = ("role", "is_staff", "is_active")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "client", "store", "user", "safe_for_platform", "created_at")
    list_filter = ("action", "safe_for_platform", "created_at")
    search_fields = ("message", "model_name", "object_id", "user__username", "client__name")


@admin.register(ClientMessage)
class ClientMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "audience", "client", "created_at")
    list_filter = ("audience", "created_at")
    search_fields = ("subject", "body", "sender__username", "client__name")


@admin.register(ClientMessageRead)
class ClientMessageReadAdmin(admin.ModelAdmin):
    list_display = ("message", "user", "read_at")
    search_fields = ("message__subject", "user__username")
