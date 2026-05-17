from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import DailyClose

@admin.register(DailyClose)
class DailyCloseAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):
    list_display = ("store", "business_date", "expected_cash", "counted_cash", "short_over", "locked")
    list_filter = ("locked", "business_date")
