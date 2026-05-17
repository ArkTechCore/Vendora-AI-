from auditlog.registry import AuditLogRegistrationError, auditlog


def register_audit_models():
    from clients.models import Client
    from dailyclose.models import DailyClose
    from inventory.models import Ingredient, InventoryCount, MenuItem, PurchaseReceive, StockMovement, Vendor
    from paidouts.models import PaidOut
    from pos_integrations.models import ImportedSale, POSConnection
    from stores.models import Store

    models = [
        Client,
        DailyClose,
        Ingredient,
        InventoryCount,
        ImportedSale,
        MenuItem,
        PaidOut,
        POSConnection,
        PurchaseReceive,
        StockMovement,
        Store,
        Vendor,
    ]
    for model in models:
        try:
            auditlog.register(model)
        except AuditLogRegistrationError:
            continue
