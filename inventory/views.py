from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.access import permission_required, role_required
from accounts.services import log_audit
from .forms import BulkReceiveForm, IngredientForm, MenuItemForm, PurchaseReceiveForm, PurchaseReceiveItemForm, RecipeIngredientFormSet, RecipeMenuItemForm, StockCountStoreForm, StockMovementForm, VendorForm
from .models import Ingredient, InventoryCount, MenuItem, PurchaseReceive, PurchaseReceiveItem, RecipeIngredient, StockMovement, Vendor
from .invoice_parser import parse_purchase_invoice
from .services import close_inventory_count

def tenant_qs(user, model):
    qs = model.objects.all()
    if user.is_super_admin():
        return qs
    if hasattr(model, "client"):
        return qs.filter(client=user.client)
    if model in (StockMovement, PurchaseReceiveItem):
        return qs.filter(ingredient__client=user.client)
    if model is PurchaseReceive:
        return qs.filter(store__client=user.client)
    return qs


def list_view(request, model, title, create_url, columns):
    return render(request, "list.html", {"title": title, "create_url": create_url, "objects": tenant_qs(request.user, model), "columns": columns})


def save_form(request, form_class, model, title, redirect_name, pk=None, set_created_by=False):
    obj = get_object_or_404(tenant_qs(request.user, model), pk=pk) if pk else None
    creating = obj is None
    form = form_class(request.POST or None, instance=obj, user=request.user)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if hasattr(saved, "client_id") and not request.user.is_super_admin():
            saved.client = request.user.client
        if hasattr(saved, "store_id") and request.user.is_manager():
            saved.store = request.user.store
        if set_created_by:
            saved.created_by = request.user
        if isinstance(saved, PurchaseReceive):
            saved.received_by = request.user
        saved.save()
        opening_quantity = form.cleaned_data.get("opening_quantity") if isinstance(saved, Ingredient) else None
        if creating and opening_quantity:
            StockMovement.objects.create(
                ingredient=saved,
                movement_type=StockMovement.ADJUSTMENT,
                quantity=opening_quantity,
                note="Opening quantity entered during ingredient setup",
                created_by=request.user,
            )
        messages.success(request, f"{title} saved.")
        return redirect(redirect_name)
    return render(request, "form.html", {"title": title, "form": form})


@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def vendor_list(request): return list_view(request, Vendor, "Vendors", "vendor_create", ["name", "contact_name", "phone", "is_active"])
@role_required("client_owner")
def vendor_form(request, pk=None): return save_form(request, VendorForm, Vendor, "Vendor", "vendor_list", pk)
@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def ingredient_list(request): return list_view(request, Ingredient, "Ingredients", "ingredient_create", ["name", "store", "category", "current_quantity", "inventory_unit", "low_stock_level", "average_cost", "last_cost", "is_active"])
@role_required("client_owner")
def ingredient_form(request, pk=None): return save_form(request, IngredientForm, Ingredient, "Ingredient", "ingredient_list", pk)
@role_required("client_owner")
def menu_item_list(request):
    return render(request, "inventory/menu_item_list.html", {
        "title": "Menu Items",
        "objects": tenant_qs(request.user, MenuItem).prefetch_related("recipe_items__ingredient"),
    })
@role_required("client_owner")
def menu_item_form(request, pk=None): return save_form(request, MenuItemForm, MenuItem, "Menu Item", "menu_item_list", pk)
@role_required("client_owner")
def recipe_form(request):
    menu_item = None
    selector = RecipeMenuItemForm(request.POST or request.GET or None, user=request.user)
    if selector.is_valid():
        menu_item = selector.cleaned_data["menu_item"]
    elif request.GET.get("menu_item"):
        menu_item = get_object_or_404(tenant_qs(request.user, MenuItem), pk=request.GET["menu_item"])

    formset = None
    if menu_item:
        formset = RecipeIngredientFormSet(
            request.POST or None,
            instance=menu_item,
            prefix="recipe",
            user=request.user,
        )
        if request.method == "POST" and selector.is_valid() and formset.is_valid():
            with transaction.atomic():
                formset.save()
            messages.success(request, f"Recipe for {menu_item.name} saved.")
            return redirect("recipe_create")

    return render(request, "inventory/recipe_builder.html", {
        "title": "Recipe Builder",
        "selector": selector,
        "formset": formset,
        "menu_item": menu_item,
    })
@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def stock_movement_list(request): return list_view(request, StockMovement, "Stock Movements", "stock_movement_create", ["ingredient", "movement_type", "quantity", "created_at"])
@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def stock_movement_form(request): return save_form(request, StockMovementForm, StockMovement, "Stock Movement", "stock_movement_list", set_created_by=True)
@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def receive_list(request):
    return render(request, "inventory/purchases_list.html", {
        "title": "Purchases",
        "objects": tenant_qs(request.user, PurchaseReceive).select_related("store", "vendor", "received_by"),
    })
@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def receive_form(request): return save_form(request, PurchaseReceiveForm, PurchaseReceive, "Purchase Receive", "receive_list")
@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def receive_item_form(request): return save_form(request, PurchaseReceiveItemForm, PurchaseReceiveItem, "Purchase Receive Item", "receive_list")


@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def inventory_count_list(request):
    counts = InventoryCount.objects.select_related("store", "counted_by")
    if request.user.is_client_owner():
        counts = counts.filter(store__client=request.user.client)
    elif request.user.is_manager():
        counts = counts.filter(store=request.user.store)
    return render(request, "inventory/counts_list.html", {"title": "Inventory Counts", "objects": counts})


@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def bulk_receive(request):
    form = BulkReceiveForm(request.POST or None, request.FILES or None, user=request.user)
    ingredient_qs = Ingredient.objects.filter(is_active=True)
    if not request.user.is_super_admin():
        ingredient_qs = ingredient_qs.filter(client=request.user.client)
    if request.user.is_manager():
        ingredient_qs = ingredient_qs.filter(store__in=[request.user.store, None])

    vendors = Vendor.objects.all()
    if not request.user.is_super_admin():
        vendors = vendors.filter(client=request.user.client)

    parsed_rows = [{"ingredient_id": "", "quantity": "", "total_cost": ""} for _ in range(20)]

    if request.method == "POST" and "parse_invoice" in request.POST:
        uploaded = request.FILES.get("invoice_file")
        if not uploaded:
            messages.error(request, "Upload a PDF invoice first.")
        else:
            try:
                parsed = parse_purchase_invoice(uploaded, ingredient_qs, vendors)
                if not parsed["text_found"]:
                    messages.error(request, "No readable text was found in this PDF. Scanned invoices will need OCR support.")
                else:
                    initial = {
                        "store": request.POST.get("store"),
                        "vendor": parsed.get("vendor_id") or request.POST.get("vendor"),
                        "invoice_number": parsed.get("invoice_number") or request.POST.get("invoice_number", ""),
                        "invoice_date": parsed.get("invoice_date") or request.POST.get("invoice_date"),
                        "tax_fees": request.POST.get("tax_fees") or 0,
                        "notes": request.POST.get("notes", ""),
                    }
                    form = BulkReceiveForm(initial=initial, user=request.user)
                    for index, row in enumerate(parsed["rows"]):
                        parsed_rows[index] = row
                    messages.success(request, f"PDF read complete. {len(parsed['rows'])} matching item row(s) found. Review before saving.")
            except Exception as exc:
                messages.error(request, f"Could not read this PDF invoice: {exc}")

    elif request.method == "POST" and form.is_valid():
        rows = []
        for index in range(20):
            ingredient_id = request.POST.get(f"ingredient_{index}")
            quantity = request.POST.get(f"quantity_{index}")
            total_cost = request.POST.get(f"unit_cost_{index}") or 0
            if not ingredient_id and not quantity:
                continue
            if not ingredient_id or not quantity:
                messages.error(request, "Each receive row needs both ingredient and quantity.")
                break
            try:
                quantity = Decimal(quantity)
                total_cost = Decimal(str(total_cost))
            except (InvalidOperation, ValueError):
                messages.error(request, "Received quantities and unit costs must be valid numbers.")
                break
            if quantity <= 0 or total_cost < 0:
                messages.error(request, "Received quantity must be greater than zero and total cost cannot be negative.")
                break
            ingredient = get_object_or_404(ingredient_qs, pk=ingredient_id)
            unit_cost = (total_cost / quantity).quantize(Decimal("0.0001")) if quantity else Decimal("0")
            rows.append((ingredient, quantity, unit_cost))
        else:
            if not rows:
                messages.error(request, "Add at least one received item.")
            else:
                with transaction.atomic():
                    receive = form.save(commit=False)
                    if request.user.is_manager():
                        receive.store = request.user.store
                    receive.received_by = request.user
                    receive.status = PurchaseReceive.POSTED
                    receive.subtotal = sum(quantity * unit_cost for _, quantity, unit_cost in rows)
                    receive.total = receive.subtotal + (receive.tax_fees or 0)
                    from django.utils import timezone
                    receive.posted_at = timezone.now()
                    receive.save()
                    for ingredient, quantity, unit_cost in rows:
                        PurchaseReceiveItem.objects.create(
                            purchase=receive,
                            ingredient=ingredient,
                            quantity_received=quantity,
                            purchase_quantity=quantity,
                            purchase_unit=ingredient.purchase_unit,
                            inventory_unit=ingredient.inventory_unit,
                            unit_cost=unit_cost,
                            total_cost=quantity * unit_cost,
                        )
                log_audit(request.user, "invoice_posted", f"Posted invoice {receive.invoice_number or receive.id} with {len(rows)} item(s).", receive)
                messages.success(request, f"Received {len(rows)} inventory items.")
                return redirect("receive_list")

    return render(request, "inventory/bulk_receive.html", {
        "title": "Bulk Receive",
        "form": form,
        "ingredients": ingredient_qs.order_by("name"),
        "parsed_rows": parsed_rows,
    })


@role_required("client_owner", "manager")
@permission_required("can_manage_inventory")
def stock_count(request):
    selector = StockCountStoreForm(request.POST or request.GET or None, user=request.user)
    store = None
    ingredients = Ingredient.objects.none()
    if selector.is_valid():
        store = selector.cleaned_data["store"]
        ingredients = Ingredient.objects.filter(client=store.client, is_active=True, store__in=[store, None]).order_by("name")

    if request.method == "POST" and selector.is_valid():
        counted_quantities = []
        is_draft = request.POST.get("draft") == "1"
        with transaction.atomic():
            for ingredient in ingredients.select_for_update():
                counted_value = request.POST.get(f"counted_{ingredient.id}", "").strip()
                if counted_value == "":
                    continue
                try:
                    counted = Decimal(counted_value)
                except (InvalidOperation, ValueError):
                    messages.error(request, f"{ingredient.name} count must be a valid number.")
                    return redirect(f"{request.path}?store={store.id}")
                if counted < 0:
                    messages.error(request, f"{ingredient.name} count cannot be negative.")
                    return redirect(f"{request.path}?store={store.id}")
                counted_quantities.append((ingredient, counted))
            if not counted_quantities:
                messages.error(request, "Enter at least one counted quantity.")
                return redirect(f"{request.path}?store={store.id}")
            count, created_count = InventoryCount.objects.get_or_create(
                store=store,
                business_date=selector.cleaned_data["business_date"],
                defaults={
                    "counted_by": request.user,
                    "notes": selector.cleaned_data.get("notes", ""),
                },
            )
            if count.is_closed:
                messages.error(request, "This inventory count date is already closed.")
                return redirect(f"{request.path}?store={store.id}")
            count.counted_by = request.user
            count.notes = selector.cleaned_data.get("notes", "")
            count.save(update_fields=["counted_by", "notes"])
            if is_draft:
                for ingredient, counted in counted_quantities:
                    from .models import InventoryCountItem
                    InventoryCountItem.objects.update_or_create(
                        count=count,
                        ingredient=ingredient,
                        defaults={"counted_quantity": counted, "unit_cost_snapshot": ingredient.average_cost},
                    )
                messages.success(request, "Inventory count draft saved.")
                return redirect("inventory_count_list")
            created = close_inventory_count(count, counted_quantities, request.user)
        log_audit(request.user, "inventory_count_posted", f"Posted inventory count for {store.name} on {count.business_date}.", count)
        messages.success(request, f"Inventory count submitted. {created} adjustment movements created.")
        return redirect("inventory_count_list")

    return render(request, "inventory/stock_count.html", {
        "title": "Stock Count",
        "selector": selector,
        "store": store,
        "ingredients": ingredients,
    })
