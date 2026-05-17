from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import Client

@admin.register(Client)
class ClientAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):
    list_display = ("name", "owner_name", "email", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "owner_name", "email")
