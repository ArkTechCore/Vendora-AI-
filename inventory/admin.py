from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import Ingredient, InventoryCount, InventoryCountItem, MenuItem, PurchaseReceive, PurchaseReceiveItem, RecipeIngredient, StockMovement, Vendor

class OpsAdmin(ImportExportModelAdmin, SimpleHistoryAdmin):
    pass


admin.site.register(Vendor, OpsAdmin)
admin.site.register(Ingredient, OpsAdmin)
admin.site.register(MenuItem, OpsAdmin)
admin.site.register(RecipeIngredient)
admin.site.register(StockMovement, OpsAdmin)
admin.site.register(InventoryCount, OpsAdmin)
admin.site.register(InventoryCountItem)
admin.site.register(PurchaseReceive, OpsAdmin)
admin.site.register(PurchaseReceiveItem)
