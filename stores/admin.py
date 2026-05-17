from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import Store

@admin.register(Store)
class StoreAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):
    list_display = ("name", "client", "code", "is_active")
    list_filter = ("is_active", "client")
    search_fields = ("name", "code", "client__name")
