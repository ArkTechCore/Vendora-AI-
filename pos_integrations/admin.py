from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import ImportedSale, ImportedSaleItem, POSConnection

class POSAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):
    pass


admin.site.register(POSConnection, POSAdmin)
admin.site.register(ImportedSale, POSAdmin)
admin.site.register(ImportedSaleItem)
