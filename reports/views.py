from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.access import permission_required
from dashboard.services import get_report_summary
from dashboard.services import get_dashboard_stats
from dashboard.services import get_platform_insights
from dashboard.services import get_profit_loss_summary
from dashboard.services import get_monthly_report_summary
from dashboard.services import _format_dashboard_stats
from inventory.services import get_actual_vs_theoretical_rows
from .forms import ActualVsTheoreticalForm, ReportExportForm
from .pdf import SimplePDF, _money, _quantity
from .services import build_report_data

@login_required
@permission_required("can_view_reports")
def reports_dashboard(request):
    month_value = request.GET.get("month") or timezone.localdate().strftime("%Y-%m")
    try:
        year, month = [int(part) for part in month_value.split("-", 1)]
    except (TypeError, ValueError):
        year, month = timezone.localdate().year, timezone.localdate().month
    if request.user.is_super_admin():
        return render(request, "reports/platform.html", {
            "stats": _format_dashboard_stats(get_dashboard_stats(request.user)),
            "platform_insights": get_platform_insights(),
            "monthly": get_monthly_report_summary(request.user, year=year, month=month),
            "selected_month": f"{year:04d}-{month:02d}",
            "export_form": ReportExportForm(user=request.user),
        })
    return render(request, "reports/dashboard.html", {
        "summary": get_report_summary(request.user),
        "profit_loss": get_profit_loss_summary(request.user),
        "monthly": get_monthly_report_summary(request.user, year=year, month=month),
        "selected_month": f"{year:04d}-{month:02d}",
        "export_form": ReportExportForm(user=request.user),
    })


@login_required
@permission_required("can_view_reports")
def report_pdf(request):
    form = ReportExportForm(request.GET or None, user=request.user)
    if not form.is_valid():
        template = "reports/platform.html" if request.user.is_super_admin() else "reports/dashboard.html"
        context = {"export_form": form}
        if request.user.is_super_admin():
            context["stats"] = _format_dashboard_stats(get_dashboard_stats(request.user))
            context["platform_insights"] = get_platform_insights()
        else:
            context["summary"] = get_report_summary(request.user)
        return render(request, template, context, status=400)

    report_type = form.cleaned_data["report_type"]
    data = build_report_data(
        request.user,
        report_type=report_type,
        store=form.cleaned_data.get("store"),
        start_date=form.cleaned_data.get("start_date"),
        end_date=form.cleaned_data.get("end_date"),
    )
    pdf = _build_pdf(data)
    response = HttpResponse(pdf, content_type="application/pdf")
    mode = "attachment" if request.GET.get("download") == "1" else "inline"
    filename = f"vendoraops-{data['report_type']}-report.pdf"
    response["Content-Disposition"] = f'{mode}; filename="{filename}"'
    return response


@login_required
@permission_required("can_view_reports")
def actual_vs_theoretical(request):
    if request.user.is_super_admin():
        return render(request, "reports/platform.html", {
            "stats": _format_dashboard_stats(get_dashboard_stats(request.user)),
            "platform_insights": get_platform_insights(),
            "export_form": ReportExportForm(user=request.user),
        })
    form = ActualVsTheoreticalForm(request.GET or None, user=request.user)
    rows = []
    start_count = None
    end_count = None
    store = None
    if form.is_valid():
        store = request.user.store if request.user.is_manager() else form.cleaned_data["store"]
        start_count = form.cleaned_data.get("start_count")
        end_count = form.cleaned_data.get("end_count")
        rows = get_actual_vs_theoretical_rows(store, start_count=start_count, end_count=end_count)
    return render(request, "reports/actual_vs_theoretical.html", {
        "form": form,
        "rows": rows,
        "store": store,
        "start_count": start_count,
        "end_count": end_count,
    })


def _build_pdf(data):
    doc = SimplePDF(data["title"])
    report_label = data["report_type"].replace("_", " ").title()
    meta = [
        ("Date", data["generated_at"].strftime("%Y-%m-%d")),
        ("Store", data["filters"]["store"]),
        ("Range", data["filters"]["date_range"]),
    ]
    if data["report_type"] == "full":
        doc.add_document_header(data["business"], [
            ("Report No.", data["generated_at"].strftime("%Y%m%d%H%M")),
            ("Date", data["generated_at"].strftime("%Y-%m-%d")),
            ("Report", report_label),
            ("Store", data["filters"]["store"]),
            ("Range", data["filters"]["date_range"]),
        ])
    else:
        doc.add_report_title(report_label, meta, logo_path=data["business"].get("logo_path"))

    if data["report_type"] == "platform":
        money_labels = {"platform_sales_handled", "inventory_value_handled"}
        doc.add_summary_grid(
            (label.replace("_", " ").title(), _money(value) if label in money_labels else f"{int(value):,}")
            for label, value in data["platform"].items()
        )
        doc.add_section("Client Scale")
        doc.add_table(
            ["Client", "Status", "Sales Handled", "Orders", "Inventory Handled", "Items", "Movements"],
            [(
                row["client"],
                row["status"],
                _money(row["sales"]),
                f"{row['orders']:,}",
                _money(row["inventory_value"]),
                f"{row['inventory_items']:,}",
                f"{row['inventory_movements']:,}",
            ) for row in data.get("platform_clients", [])],
            [("Client", 100, "left"), ("Status", 68, "left", False), ("Sales", 82, "right", False), ("Orders", 58, "right", False), ("Inventory", 86, "right", False), ("Items", 58, "right", False), ("Moves", 76, "right", False)],
        )
        doc.add_footer(
            "Platform-safe VendoraOps report. Client operating details, paid-out notes, vendor pricing, and store-level data are excluded.",
            logo_path=data["business"].get("logo_path"),
        )
        return doc.render()

    summary = data["summary"]
    report_type = data["report_type"]
    if report_type == "full":
        doc.add_summary_grid([
            ("Total Sales", _money(summary["sales"])),
            ("Net Sales", _money(summary["net_sales"])),
            ("Food COGS", _money(summary["food_cogs"])),
            ("Gross Profit", _money(summary["gross_profit"])),
            ("Operating Expenses", _money(summary["operating_expenses"])),
            ("Inventory Paid-Outs", _money(summary["inventory_paidouts"])),
            ("Cash Sales", _money(summary["cash_sales"])),
            ("Card Sales", _money(summary["card_sales"])),
            ("Cash Paid-Outs", _money(summary["cash_paidouts"])),
            ("Short / Over", _money(summary["short_over"])),
            ("Net Profit", _money(summary["net_profit"])),
            ("Inventory Value", _money(summary["inventory_value"])),
            ("Low Stock Items", summary["low_stock_count"]),
            ("Processed Sales", summary["processed_sales"]),
            ("Unprocessed Sales", summary["unprocessed_sales"]),
        ])

    if report_type in {"full", "sales"}:
        doc.add_section("Sales")
        doc.add_table(
            ["Date", "Order", "Store", "Items", "Total", "Cash", "Card"],
            [(
                s.business_date,
                _order_label(s.external_order_id),
                s.connection.store.name,
                ", ".join(f"{item.item_name} x{_quantity(item.quantity)}" for item in s.items.all()) or "-",
                _money(s.total_amount),
                _money(s.cash_amount),
                _money(s.card_amount),
            ) for s in data["sales"].prefetch_related("items").select_related("connection__store")],
            [("Date", 68, "left", False), ("Order", 86, "left", False), ("Store", 78, "left"), ("Items", 135, "left"), ("Total", 56, "right", False), ("Cash", 51, "right", False), ("Card", 54, "right", False)],
        )
        doc.add_totals_block([
            ("Total Sales", _money(summary["sales"])),
            ("Cash Sales", _money(summary["cash_sales"])),
            ("Card Sales", _money(summary["card_sales"])),
        ])

    if report_type in {"full", "paidouts"}:
        doc.add_section("Paid-Outs")
        doc.add_table(
            ["Date", "Store", "Category", "Paid To", "Note", "Source", "Amount"],
            [(p.business_date or p.created_at.date(), p.store.name, p.get_category_display(), p.vendor_payee or "-", p.description, p.payment_source.title(), _money(p.amount)) for p in data["paidouts"]],
            [("Date", 68, "left", False), ("Store", 76, "left"), ("Category", 88, "left"), ("Paid To", 84, "left"), ("Note", 112, "left"), ("Source", 48, "left", False), ("Amount", 52, "right", False)],
        )
        doc.add_totals_block([
            ("Total Paid-Outs", _money(summary["paidouts"])),
            ("Cash Paid-Outs", _money(summary["cash_paidouts"])),
        ])

    if report_type in {"full", "daily_close"}:
        doc.add_section("Daily Close")
        doc.add_table(
            ["Date", "Store", "Opening", "Cash Sales", "Paid-Outs", "Expected", "Counted", "Short/Over"],
            [(c.business_date, c.store.name, _money(c.opening_cash), _money(c.cash_sales), _money(c.cash_paidouts), _money(c.expected_cash), _money(c.counted_cash), _money(c.short_over)) for c in data["daily_closes"]],
            [("Date", 66, "left", False), ("Store", 72, "left"), ("Opening", 62, "right", False), ("Cash Sales", 68, "right", False), ("Paid-Outs", 68, "right", False), ("Expected", 64, "right", False), ("Counted", 62, "right", False), ("Short/Over", 66, "right", False)],
        )
        doc.add_totals_block([("Total Short / Over", _money(summary["short_over"]))])

    if report_type in {"full", "purchases"}:
        doc.add_section("Purchases")
        doc.add_table(
            ["Date", "Store", "Vendor", "Invoice", "Item", "Qty", "Cost"],
            [(
                item.purchase.invoice_date or item.purchase.received_at.date(),
                item.purchase.store.name,
                item.purchase.vendor.name if item.purchase.vendor else "-",
                item.purchase.invoice_number or "-",
                item.ingredient.name,
                f"{_quantity(item.quantity_received)} {item.inventory_unit or item.ingredient.inventory_unit}",
                _money(item.total_cost),
            ) for item in data["purchase_items"]],
            [("Date", 66, "left", False), ("Store", 78, "left"), ("Vendor", 100, "left"), ("Invoice", 70, "left", False), ("Item", 98, "left"), ("Qty", 58, "right", False), ("Cost", 58, "right", False)],
        )
        doc.add_totals_block([("Total Purchases", _money(sum(item.total_cost for item in data["purchase_items"])))])

    if report_type in {"full", "inventory"}:
        if report_type == "inventory":
            doc.add_section("Inventory Counts")
            doc.add_table(
                ["Date", "Store", "Who", "Ingredient", "Expected", "Counted", "Unit", "Value"],
                [(
                    item.count.business_date,
                    item.count.store.name,
                    item.count.counted_by.username,
                    item.ingredient.name,
                    _quantity(item.ingredient.current_quantity),
                    _quantity(item.counted_quantity),
                    item.ingredient.inventory_unit,
                    _money(item.counted_value),
                ) for item in data["inventory_count_items"]],
                [("Date", 70, "left", False), ("Store", 76, "left"), ("Who", 48, "left", False), ("Ingredient", 106, "left"), ("Expected", 58, "right", False), ("Counted", 58, "right", False), ("Unit", 42, "left", False), ("Value", 70, "right", False)],
            )
        doc.add_section("Low Stock")
        doc.add_table(
            ["Ingredient", "Current", "Low", "Unit", "Value"],
            [(i.name, _quantity(i.current_quantity), _quantity(i.low_stock_level), i.inventory_unit, _money(i.value_estimate)) for i in data["low_stock"]],
            [("Ingredient", 190, "left"), ("Current", 88, "right", False), ("Low", 88, "right", False), ("Unit", 72, "left", False), ("Value", 90, "right", False)],
        )
        if report_type == "full":
            doc.add_section("Inventory Counts")
            doc.add_table(
                ["Date", "Store", "Status", "Counted By"],
                [(c.business_date, c.store.name, c.status, c.counted_by.username) for c in data["inventory_counts"]],
                [("Date", 90, "left", False), ("Store", 190, "left"), ("Status", 100, "left", False), ("Counted By", 148, "left", False)],
            )

    doc.add_footer(logo_path=data["business"].get("logo_path"))
    return doc.render()


def _order_label(order_id):
    text = str(order_id or "-")
    if text.startswith("QSLOAD-"):
        return text.removeprefix("QSLOAD-")
    return text
