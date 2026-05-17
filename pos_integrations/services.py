from django.db import transaction
from django.utils import timezone

from inventory.models import MenuItem, RecipeIngredient, StockMovement
from .adapters import get_adapter
from .models import ImportedSale, ImportedSaleItem


@transaction.atomic
def import_normalized_sale(connection, payload):
    sale, created = ImportedSale.objects.update_or_create(
        connection=connection,
        external_order_id=payload.external_order_id,
        defaults={
            "business_date": payload.business_date,
            "total_amount": payload.total_amount,
            "cash_amount": payload.cash_amount,
            "card_amount": payload.card_amount,
            "status": "imported",
        },
    )
    if not created and sale.processed_inventory:
        return sale, False
    sale.items.all().delete()
    for item in payload.items:
        ImportedSaleItem.objects.create(
            sale=sale,
            external_item_id=item.external_item_id,
            item_name=item.item_name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            mapped_menu_item_id=item.mapped_menu_item_id,
        )
    return sale, created


def sync_pos_connection(connection, start_date=None, end_date=None):
    adapter = get_adapter(connection)
    try:
        imported = 0
        for payload in adapter.fetch_sales(start_date=start_date, end_date=end_date):
            import_normalized_sale(connection, payload)
            imported += 1
        connection.last_sync_at = timezone.now()
        connection.sync_status = "success"
        connection.last_error = ""
        connection.save(update_fields=["last_sync_at", "sync_status", "last_error"])
        return imported
    except Exception as exc:
        connection.sync_status = "failed"
        connection.last_error = str(exc)
        connection.save(update_fields=["sync_status", "last_error"])
        raise


@transaction.atomic
def process_sale_inventory(sale, user):
    sale = sale.__class__.objects.select_for_update().get(pk=sale.pk)
    if sale.processed_inventory:
        return 0
    movements = 0
    for item in sale.items.select_related("mapped_menu_item").all():
        menu_item = item.mapped_menu_item
        if menu_item is None:
            menu_item = MenuItem.objects.filter(
                client=sale.connection.client,
                external_pos_id=item.external_item_id,
                is_active=True,
            ).first()
        if menu_item is None:
            menu_item = MenuItem.objects.filter(
                client=sale.connection.client,
                external_pos_name__iexact=item.item_name,
                is_active=True,
            ).first()
        if menu_item is None:
            menu_item = MenuItem.objects.filter(
                client=sale.connection.client,
                name__iexact=item.item_name,
                is_active=True,
            ).first()
        if menu_item and item.mapped_menu_item_id != menu_item.id:
            item.mapped_menu_item = menu_item
            item.save(update_fields=["mapped_menu_item"])
        if not menu_item:
            continue
        for recipe in RecipeIngredient.objects.filter(menu_item=menu_item).select_related("ingredient"):
            StockMovement.objects.create(
                ingredient=recipe.ingredient,
                movement_type=StockMovement.POS_DEDUCTION,
                quantity=recipe.quantity_used * item.quantity,
                note=f"Theoretical POS usage estimate from sale {sale.external_order_id}: {item.item_name}",
                created_by=user,
                source_sale_id=sale.external_order_id,
            )
            movements += 1
    sale.processed_inventory = True
    sale.processed_theoretical_usage = True
    sale.status = "processed"
    sale.save(update_fields=["processed_inventory", "processed_theoretical_usage", "status"])
    return movements
