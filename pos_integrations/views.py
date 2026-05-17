from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.access import permission_required, role_required
from accounts.services import log_audit
from inventory.models import MenuItem
from .forms import ImportedSaleForm, ImportedSaleItemForm, ManualSalesEntryForm, POSConnectionForm
from .models import ImportedSale, ImportedSaleItem, POSConnection
from .readiness import OPEN_SOURCE_UPGRADE_STACK, PROVIDER_REQUIREMENTS
from .services import process_sale_inventory, sync_pos_connection

def scope(user, model):
    qs = model.objects.all()
    if user.is_super_admin():
        return qs
    if model is POSConnection:
        qs = qs.filter(client=user.client)
        return qs.filter(store=user.store) if user.is_manager() else qs
    if model is ImportedSale:
        qs = qs.filter(connection__client=user.client)
        return qs.filter(connection__store=user.store) if user.is_manager() else qs
    qs = qs.filter(sale__connection__client=user.client)
    return qs.filter(sale__connection__store=user.store) if user.is_manager() else qs


def generic_form(request, form_class, model, title, redirect_name, pk=None):
    obj = get_object_or_404(scope(request.user, model), pk=pk) if pk else None
    form = form_class(request.POST or None, instance=obj, user=request.user)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if isinstance(saved, POSConnection) and request.user.is_client_owner():
            saved.client = request.user.client
        saved.save()
        messages.success(request, f"{title} saved.")
        return redirect(redirect_name)
    return render(request, "form.html", {"title": title, "form": form})


@role_required("client_owner", "manager")
@permission_required("can_manage_pos")
def connection_list(request):
    return render(request, "pos_integrations/connection_list.html", {
        "title": "POS Connections",
        "objects": scope(request.user, POSConnection),
        "provider_requirements": PROVIDER_REQUIREMENTS,
        "upgrade_stack": OPEN_SOURCE_UPGRADE_STACK,
    })


@role_required("client_owner")
def connection_form(request, pk=None):
    obj = get_object_or_404(scope(request.user, POSConnection), pk=pk) if pk else None
    form = POSConnectionForm(request.POST or None, instance=obj, user=request.user)
    if request.method == "POST" and form.is_valid():
        connection = form.save()
        log_audit(request.user, "pos_connection_saved", f"POS API settings saved for {connection.store.name}.", connection, client=connection.client, store=connection.store)
        messages.success(request, "POS API setting saved. The key is hidden now; leave it blank next time to keep it unchanged.")
        return redirect("pos_connection_list")
    return render(request, "pos_integrations/connection_form.html", {"title": "POS API setting", "form": form, "connection": obj})


@role_required("client_owner", "manager")
@permission_required("can_manage_pos")
def sale_list(request):
    return render(request, "pos_integrations/sale_list.html", {"title": "Imported Sales", "objects": scope(request.user, ImportedSale)})


@role_required("client_owner", "manager")
@permission_required("can_manage_pos")
def sale_form(request, pk=None): return generic_form(request, ImportedSaleForm, ImportedSale, "Imported Sale", "sale_list", pk)


@role_required("client_owner", "manager")
@permission_required("can_manage_pos")
def sale_item_form(request, pk=None): return generic_form(request, ImportedSaleItemForm, ImportedSaleItem, "Sale Item", "sale_list", pk)


@role_required("client_owner", "manager")
@permission_required("can_manage_pos")
def manual_sales_entry(request):
    form = ManualSalesEntryForm(request.POST or None, user=request.user)
    menu_items = MenuItem.objects.filter(is_active=True).order_by("category", "name")
    if request.user.is_client_owner():
        menu_items = menu_items.filter(client=request.user.client)
    elif request.user.is_manager():
        menu_items = menu_items.filter(client=request.user.client, store__in=[request.user.store, None])

    if request.method == "POST" and form.is_valid():
        store = form.cleaned_data["store"]
        business_date = form.cleaned_data["business_date"]
        rows = []
        mapped_total = Decimal("0")
        for item in menu_items:
            try:
                qty = Decimal(str(request.POST.get(f"qty_{item.id}") or "0"))
            except InvalidOperation:
                messages.error(request, f"Quantity for {item.name} must be a number.")
                break
            if qty <= 0:
                continue
            line_total = qty * item.selling_price
            rows.append((item, qty, line_total))
            mapped_total += line_total
        else:
            custom_amount = form.cleaned_data.get("custom_sales_amount") or Decimal("0")
            cash = form.cleaned_data["cash_amount"]
            card = form.cleaned_data["card_amount"]
            tax = form.cleaned_data.get("tax_amount") or Decimal("0")
            tip = form.cleaned_data.get("tip_amount") or Decimal("0")
            discount = form.cleaned_data.get("discount_amount") or Decimal("0")
            expected_total = mapped_total + custom_amount + tax + tip - discount
            entered_total = cash + card
            if expected_total != entered_total:
                messages.error(request, f"Cash + card must equal mapped/custom sales plus tax/tip minus discounts. Expected ${expected_total:,.2f}.")
            elif not rows and not custom_amount:
                messages.error(request, "Add at least one menu item quantity or a custom sales amount.")
            else:
                with transaction.atomic():
                    connection = POSConnection.objects.filter(
                        client=store.client,
                        store=store,
                        provider="csv",
                        connection_name="Manual end-of-day sales",
                    ).first()
                    if not connection:
                        connection = POSConnection.objects.create(
                            client=store.client,
                            store=store,
                            provider="csv",
                            connection_name="Manual end-of-day sales",
                            environment="production",
                            is_active=True,
                        )
                    sale = ImportedSale.objects.create(
                        connection=connection,
                        external_order_id=f"MANUAL-{business_date:%Y%m%d}-{timezone.now():%H%M%S}",
                        business_date=business_date,
                        total_amount=entered_total,
                        cash_amount=cash,
                        card_amount=card,
                        tax_amount=tax,
                        tip_amount=tip,
                        discount_amount=discount,
                        status="manual",
                    )
                    for item, qty, _line_total in rows:
                        ImportedSaleItem.objects.create(
                            sale=sale,
                            external_item_id=item.external_pos_id or str(item.id),
                            item_name=item.name,
                            quantity=qty,
                            unit_price=item.selling_price,
                            mapped_menu_item=item,
                        )
                    if custom_amount:
                        ImportedSaleItem.objects.create(
                            sale=sale,
                            external_item_id="custom",
                            item_name="Custom / unmapped sales",
                            quantity=1,
                            unit_price=custom_amount,
                        )
                    movements = process_sale_inventory(sale, request.user)
                log_audit(request.user, "manual_sales_entered", f"Manual sales entered for {store.name} on {business_date}.", sale, client=store.client, store=store)
                messages.success(request, f"Manual sales saved. {movements} inventory movement(s) created from mapped items.")
                return redirect("sale_list")

    return render(request, "pos_integrations/manual_sales.html", {"form": form, "menu_items": menu_items})


@role_required("client_owner", "manager")
@permission_required("can_manage_pos")
def process_sale(request, pk):
    sale = get_object_or_404(scope(request.user, ImportedSale), pk=pk)
    count = process_sale_inventory(sale, request.user)
    log_audit(request.user, "theoretical_usage_processed", f"Processed theoretical usage for sale {sale.id}.", sale, client=sale.connection.client, store=sale.connection.store)
    messages.success(request, f"Inventory processed. {count} stock movements created.")
    return redirect("sale_list")


@role_required("client_owner")
def sync_connection(request, pk):
    connection = get_object_or_404(scope(request.user, POSConnection), pk=pk)
    try:
        count = sync_pos_connection(connection)
        messages.success(request, f"POS sync complete. {count} sale(s) imported.")
    except NotImplementedError:
        messages.error(request, "This provider is ready in the architecture, but live API sync is not connected yet. Use manual/CSV import for now.")
    except Exception as exc:
        messages.error(request, f"POS sync failed: {exc}")
    return redirect("pos_connection_list")
