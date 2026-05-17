from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import PaidOut

@admin.register(PaidOut)
class PaidOutAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):
    list_display = ("store", "amount", "category", "payment_source", "approved", "locked", "created_at")
    list_filter = ("category", "payment_source", "approved", "locked")
