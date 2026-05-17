from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from pos_integrations.models import ImportedSaleItem
from .models import InventoryCount, InventoryCountItem, PurchaseReceiveItem, RecipeIngredient, StockMovement


@transaction.atomic
def close_inventory_count(count, counted_quantities, user):
    count = InventoryCount.objects.select_for_update().get(pk=count.pk)
    if count.is_closed:
        return 0

    adjustments = 0
    for ingredient, counted in counted_quantities:
        InventoryCountItem.objects.update_or_create(
            count=count,
            ingredient=ingredient,
            defaults={
                "counted_quantity": counted,
                "unit_cost_snapshot": ingredient.cost_per_unit,
            },
        )
        if counted != ingredient.current_quantity:
            StockMovement.objects.create(
                ingredient=ingredient,
                movement_type=StockMovement.ADJUSTMENT,
                quantity=counted,
                note=f"Closed inventory count for {count.store.name} on {count.business_date}",
                created_by=user,
            )
            adjustments += 1

    count.status = InventoryCount.CLOSED
    count.closed_at = timezone.now()
    count.save(update_fields=["status", "closed_at"])
    return adjustments


def get_actual_vs_theoretical_rows(store, start_count=None, end_count=None):
    counts = InventoryCount.objects.filter(store=store, status=InventoryCount.CLOSED).order_by("-business_date")
    if end_count is None:
        end_count = counts.first()
    if start_count is None and end_count:
        start_count = counts.filter(business_date__lt=end_count.business_date).first()
    if not start_count or not end_count:
        return []

    start_date = start_count.business_date
    end_date = end_count.business_date
    ingredient_ids = set(start_count.items.values_list("ingredient_id", flat=True)) | set(end_count.items.values_list("ingredient_id", flat=True))

    start = {item.ingredient_id: item for item in start_count.items.select_related("ingredient")}
    end = {item.ingredient_id: item for item in end_count.items.select_related("ingredient")}

    purchases = PurchaseReceiveItem.objects.filter(
        purchase__store=store,
        purchase__received_at__date__gt=start_date,
        purchase__received_at__date__lte=end_date,
    ).values("ingredient_id").annotate(qty=Sum("quantity_received"))
    purchase_qty = {row["ingredient_id"]: row["qty"] or Decimal("0") for row in purchases}
    ingredient_ids |= set(purchase_qty)

    waste = StockMovement.objects.filter(
        ingredient__store__in=[store, None],
        ingredient__client=store.client,
        movement_type=StockMovement.WASTE,
        created_at__date__gt=start_date,
        created_at__date__lte=end_date,
    ).values("ingredient_id").annotate(qty=Sum("quantity"))
    waste_qty = {row["ingredient_id"]: row["qty"] or Decimal("0") for row in waste}
    ingredient_ids |= set(waste_qty)

    theoretical_qty = defaultdict(lambda: Decimal("0"))
    sale_items = ImportedSaleItem.objects.filter(
        sale__connection__store=store,
        sale__business_date__gt=start_date,
        sale__business_date__lte=end_date,
    ).select_related("mapped_menu_item")
    for sale_item in sale_items:
        menu_item = sale_item.mapped_menu_item
        if not menu_item:
            continue
        for recipe in RecipeIngredient.objects.filter(menu_item=menu_item).select_related("ingredient"):
            theoretical_qty[recipe.ingredient_id] += recipe.quantity_used * sale_item.quantity
            ingredient_ids.add(recipe.ingredient_id)

    rows = []
    for ingredient_id in sorted(ingredient_ids):
        start_item = start.get(ingredient_id)
        end_item = end.get(ingredient_id)
        ingredient = (start_item or end_item).ingredient if (start_item or end_item) else None
        if ingredient is None:
            from .models import Ingredient
            ingredient = Ingredient.objects.get(pk=ingredient_id)
        begin_qty = start_item.counted_quantity if start_item else Decimal("0")
        end_qty = end_item.counted_quantity if end_item else Decimal("0")
        purchased = purchase_qty.get(ingredient_id, Decimal("0"))
        actual = begin_qty + purchased - end_qty
        theoretical = theoretical_qty[ingredient_id]
        variance = actual - theoretical
        unit_cost = end_item.unit_cost_snapshot if end_item else ingredient.cost_per_unit
        theoretical_value = theoretical * unit_cost
        actual_value = actual * unit_cost
        variance_value = variance * unit_cost
        variance_percent = (variance / theoretical * 100) if theoretical else None
        rows.append({
            "ingredient": ingredient,
            "begin_qty": begin_qty,
            "purchases": purchased,
            "end_qty": end_qty,
            "actual_qty": actual,
            "theoretical_qty": theoretical,
            "variance_qty": variance,
            "waste_qty": waste_qty.get(ingredient_id, Decimal("0")),
            "unit_cost": unit_cost,
            "actual_value": actual_value,
            "theoretical_value": theoretical_value,
            "variance_value": variance_value,
            "variance_percent": variance_percent,
            "status": "Urgent" if variance_percent is not None and abs(variance_percent) >= 7 else "Watch" if variance_percent is not None and abs(variance_percent) >= 3 else "OK",
        })
    return rows
