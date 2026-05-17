import json
import logging
import re
import urllib.error
import urllib.request
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, F, Sum
from django.utils import timezone

from dailyclose.models import DailyClose
from inventory.models import Ingredient
from paidouts.models import PaidOut
from pos_integrations.models import ImportedSale
from stores.models import Store
from vendoraops.mongodb import AI_REPORTS, INVESTIGATION_REPORTS, insert_document, ping_mongodb
from .models import AIReport


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an operational restaurant audit intelligence system. Investigate "
    "restaurant business records, detect suspicious paidouts, inventory variance, "
    "cash leakage, abnormal spending, control gaps, and profit/loss issues. "
    "Do not provide generic advice or conversational commentary. Use only the "
    "provided operating data as evidence. Return concise audit findings, risk "
    "level, explanations, reconciliation requirements, and practical control "
    "recommendations for a restaurant operator."
)


def accessible_stores(user):
    qs = Store.objects.filter(is_active=True).select_related("client")
    if user.is_super_admin():
        return qs
    if user.is_client_owner():
        return qs.filter(client=user.client)
    return qs.filter(pk=user.store_id)


def default_store_for(user):
    return accessible_stores(user).first()


def analyze_operations(user, store_id=None, date_range="yesterday", question="Analyze operations"):
    store = _get_store(user, store_id)
    data = collect_operational_data(store, date_range=date_range)
    report = _call_gemini(data, question) or build_local_audit(data, question)
    source = "gemini" if report.get("_source") == "gemini" else "rule_based"
    report.pop("_source", None)
    report = clean_report_for_display(report)
    saved = AIReport.objects.create(store=store, date_range=date_range, question=question, report=report, source=source)
    mongo_id = mirror_report_to_mongo(saved, data, audit_type="operational_audit")
    if mongo_id:
        saved.mongo_document_id = mongo_id
        saved.save(update_fields=["mongo_document_id"])
    return {"id": saved.id, "store": store.name, "source": source, "report": report}


def investigate_finding(user, store_id=None, finding_id=None, context=""):
    store = _get_store(user, store_id)
    current = collect_operational_data(store, date_range="week")
    latest = AIReport.objects.filter(store=store).first()
    report_context = latest.report if latest else {}
    question = (
        "Investigate this risk pattern against the prior seven days. Compare "
        "paidout totals by employee, repeated inventory shortages, recurring "
        "cash movement anomalies, and operational control gaps. "
        f"Finding id/title: {finding_id or 'selected finding'}. Context: {context}"
    )
    data = {
        **current,
        "latest_ai_report": report_context,
        "investigation_context": context,
    }
    report = _call_gemini(data, question) or build_local_investigation(data, finding_id, context)
    source = "gemini" if report.get("_source") == "gemini" else "rule_based"
    report.pop("_source", None)
    report = clean_report_for_display(report)
    saved = AIReport.objects.create(store=store, date_range="investigation", question=question, report=report, source=source)
    mongo_id = mirror_investigation_to_mongo(saved, data, finding_id=finding_id, context=context)
    if mongo_id:
        saved.mongo_document_id = mongo_id
        saved.save(update_fields=["mongo_document_id"])
    return {"id": saved.id, "store": store.name, "source": source, "report": report}


def collect_operational_data(store, date_range="yesterday"):
    today = timezone.localdate()
    if date_range == "today":
        start = end = today
    elif date_range == "week":
        start, end = today - timedelta(days=6), today
    else:
        start = end = today - timedelta(days=1)

    paidouts = PaidOut.objects.filter(store=store, business_date__gte=start, business_date__lte=end).select_related("created_by")
    inventory = Ingredient.objects.filter(client=store.client, is_active=True).filter(store__in=[store, None]).order_by("name")
    sales = ImportedSale.objects.filter(connection__store=store, business_date__gte=start, business_date__lte=end)
    closes = DailyClose.objects.filter(store=store, business_date__gte=start, business_date__lte=end)
    previous_start = start - timedelta(days=7)
    previous_paidouts = PaidOut.objects.filter(store=store, business_date__gte=previous_start, business_date__lt=start)
    historical_paidouts = PaidOut.objects.filter(store=store, business_date__gte=previous_start, business_date__lte=end).select_related("created_by")
    historical_sales = ImportedSale.objects.filter(connection__store=store, business_date__gte=previous_start, business_date__lte=end)

    paidout_rows = [_paidout_row(p) for p in paidouts]
    inventory_rows = [_inventory_row(i) for i in inventory]
    sales_total = sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    cash_sales = sales.aggregate(total=Sum("cash_amount"))["total"] or Decimal("0")
    card_sales = sales.aggregate(total=Sum("card_amount"))["total"] or Decimal("0")
    paidout_total = paidouts.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    inventory_value = sum((i.value_estimate for i in inventory), Decimal("0"))
    short_over = closes.aggregate(total=Sum("short_over"))["total"] or Decimal("0")
    estimated_profit = sales_total - paidout_total + short_over
    paidout_to_sales_ratio = (paidout_total / sales_total) if sales_total else Decimal("0")
    historical_patterns = build_historical_patterns(historical_paidouts, historical_sales, inventory_rows)

    return {
        "store": {"id": store.id, "name": store.name, "client": store.client.name},
        "dateRange": date_range,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "salesSummary": {
            "totalSales": _num(sales_total),
            "cashSales": _num(cash_sales),
            "cardSales": _num(card_sales),
            "transactions": sales.count(),
        },
        "profitLoss": {
            "paidouts": _num(paidout_total),
            "inventoryValue": _num(inventory_value),
            "cashVariance": _num(short_over),
            "estimatedProfit": _num(estimated_profit),
            "paidoutToSalesRatio": round(_num(paidout_to_sales_ratio), 4),
        },
        "paidouts": paidout_rows,
        "inventory": inventory_rows,
        "lowStock": [row for row in inventory_rows if row["isLowStock"]],
        "previousPaidoutPattern": [
            {"manager": row["created_by__username"] or "Unknown", "total": _num(row["total"]), "count": row["count"]}
            for row in previous_paidouts.values("created_by__username").annotate(total=Sum("amount"), count=Count("id"))
        ],
        "historicalPatterns": historical_patterns,
        "heuristics": build_heuristics(paidout_rows, inventory_rows, sales_total, paidout_total),
    }


def dashboard_context(user, store_id=None):
    stores = accessible_stores(user)
    store = stores.filter(pk=store_id).first() if store_id else stores.first()
    if not store:
        return {"stores": [], "selected_store": None}
    date_range = "yesterday"
    data = collect_operational_data(store, date_range=date_range)
    latest = AIReport.objects.filter(store=store).first()
    suspicious = [p for p in data["paidouts"] if p["suspicious"]]
    report = clean_report_for_display(latest.report if latest else build_local_audit(data, "Initial operational assessment"))
    source_label = _source_label(latest.source if latest else report.get("_source", "rule_based"))
    return {
        "stores": stores,
        "selected_store": store,
        "data": data,
        "latest_report": report,
        "latest_report_id": latest.id if latest else None,
        "latest_report_source": source_label,
        "latest_analyzed_at": latest.created_at if latest else None,
        "risk_level": report.get("riskLevel", "medium"),
        "risk_score": report.get("riskScore", 0),
        "audit_period": _period_label(data),
        "paidout_ratio_percent": data["profitLoss"]["paidoutToSalesRatio"] * 100,
        "kpi_trends": _kpi_trends(data),
        "suspicious_paidouts": suspicious,
        "recent_reports": AIReport.objects.filter(store=store)[:5],
        "mongodb_status": _mongodb_status_label(),
    }


def build_historical_patterns(paidouts, sales, inventory_rows):
    by_employee = []
    for row in paidouts.values("created_by__username", "created_by__first_name", "created_by__last_name").annotate(total=Sum("amount"), count=Count("id")).order_by("-total"):
        name = " ".join(part for part in [row["created_by__first_name"], row["created_by__last_name"]] if part).strip()
        by_employee.append({
            "employee": name or row["created_by__username"] or "Unknown",
            "total": _num(row["total"]),
            "count": row["count"],
        })
    sales_by_day = {
        row["business_date"].isoformat(): _num(row["total"])
        for row in sales.values("business_date").annotate(total=Sum("total_amount")).order_by("business_date")
    }
    paidouts_by_day = {
        row["business_date"].isoformat(): _num(row["total"])
        for row in paidouts.values("business_date").annotate(total=Sum("amount")).order_by("business_date")
    }
    repeated_shortages = [
        {
            "item": item["name"],
            "category": item["category"],
            "currentStock": item["currentStock"],
            "reorderLevel": item["reorderLevel"],
        }
        for item in inventory_rows
        if item["isLowStock"]
    ]
    cash_adjustments = paidouts.filter(description__icontains="cash adjustment").count()
    high_cash_paidouts = paidouts.filter(payment_source="cash", amount__gte=150).count()
    return {
        "paidoutsByEmployee": by_employee,
        "salesByDay": sales_by_day,
        "paidoutsByDay": paidouts_by_day,
        "repeatedInventoryShortages": repeated_shortages,
        "cashAdjustmentCount": cash_adjustments,
        "highCashPaidoutCount": high_cash_paidouts,
    }


def build_heuristics(paidouts, inventory, sales_total, paidout_total):
    reasons = []
    suspicious = [p for p in paidouts if p["suspicious"]]
    low_stock = [i for i in inventory if i["isLowStock"]]
    if suspicious:
        reasons.append(f"{len(suspicious)} suspicious paidout(s), including {suspicious[0]['reason']}.")
    if paidout_total and sales_total and Decimal(str(paidout_total)) > Decimal(str(sales_total)) * Decimal("0.12"):
        reasons.append("Paidouts exceed 12% of sales for the period.")
    if low_stock:
        reasons.append(f"{len(low_stock)} inventory item(s) are below reorder level.")
    chicken = next((i for i in inventory if "chicken" in i["name"].lower()), None)
    oil = next((i for i in inventory if "oil" in i["name"].lower()), None)
    if chicken and chicken["currentStock"] <= chicken["reorderLevel"]:
        reasons.append("Chicken inventory is below reorder level and needs sales-to-usage review.")
    if oil and oil["currentStock"] <= oil["reorderLevel"]:
        reasons.append("Oil usage appears high or stock is below target.")
    return reasons


def build_local_audit(data, question):
    findings = []
    suspicious = [p for p in data["paidouts"] if p["suspicious"]]
    low_stock = data["lowStock"]
    paidout_ratio = 0
    if data["salesSummary"]["totalSales"]:
        paidout_ratio = data["profitLoss"]["paidouts"] / data["salesSummary"]["totalSales"]
    if suspicious:
        paidout = suspicious[0]
        findings.append({
            "id": "paidout-cash-adjustment",
            "category": "Cash control",
            "title": "Cash movement requires reconciliation",
            "severity": "high",
            "evidence": [
                f"${paidout['amount']:,.2f} paidout for {paidout['reason']}",
                f"Created by {paidout['employee']} via {paidout['paymentMethod']}",
            ],
            "explanation": "The amount, description, and cash source indicate a control gap with potential cash leakage exposure.",
            "recommendation": "Reconcile the transaction against the register close, receipt image, manager approval, and cash drawer variance before the next close.",
        })
    if low_stock:
        names = ", ".join(item["name"] for item in low_stock[:4])
        findings.append({
            "id": "inventory-waste",
            "category": "Inventory variance",
            "title": "Inventory pressure is affecting operating margin",
            "severity": "medium" if not suspicious else "high",
            "evidence": [f"Low-stock items: {names}", *data["heuristics"][:2]],
            "explanation": "Low stock on core ingredients increases emergency purchase risk and can indicate usage variance when sales volume does not support the drawdown.",
            "recommendation": "Perform a controlled count on chicken, fryer oil, and the lowest-stock ingredients, then compare usage against item sales and prep sheets.",
        })
    if paidout_ratio > 0.12:
        findings.append({
            "id": "paidout-ratio",
            "category": "Expense control",
            "title": "Paidout-to-sales ratio exceeds operating threshold",
            "severity": "high",
            "evidence": [f"Paidouts are {paidout_ratio:.1%} of sales for the audit period."],
            "explanation": "Paidouts at this level materially reduce operating profit and require tighter approval controls.",
            "recommendation": "Require owner approval for cash paidouts above $150 and review paidout totals by manager every week.",
        })
    risk_score = min(95, 30 + len(suspicious) * 25 + len(low_stock) * 4 + int(paidout_ratio * 100))
    if risk_score >= 70:
        risk = "high"
    elif risk_score >= 40:
        risk = "medium"
    else:
        risk = "low"
    return {
        "_source": "rule_based",
        "summary": f"{data['store']['name']} shows {risk} operational risk driven by paidouts and inventory pressure.",
        "riskLevel": risk,
        "riskScore": risk_score,
        "findings": findings or [{
            "id": "baseline",
            "category": "Operating controls",
            "title": "No material anomaly detected",
            "severity": "low",
            "evidence": ["Paidouts and inventory are within current operating thresholds."],
            "explanation": "The current audit period does not show a material exception based on configured rules.",
            "recommendation": "Continue weekly inventory counts and manager approval review for paidouts.",
        }],
        "nextActions": [
            "Verify receipts for all cash paidouts above $150.",
            "Run a same-day inventory count for chicken and fryer oil.",
            "Compare manager paidout totals across the previous seven days.",
        ],
    }


def build_local_investigation(data, finding_id, context):
    paidouts = data["paidouts"]
    by_employee = Counter(p["employee"] for p in paidouts)
    repeated = by_employee.most_common(1)[0] if by_employee else ("No employee", 0)
    historical = data.get("historicalPatterns", {})
    top_employee = (historical.get("paidoutsByEmployee") or [{"employee": repeated[0], "count": repeated[1], "total": 0}])[0]
    shortages = historical.get("repeatedInventoryShortages", [])
    cash_adjustments = historical.get("cashAdjustmentCount", 0)
    return {
        "_source": "rule_based",
        "summary": "Historical comparison identified recurring cash-control exposure and inventory pressure across the prior seven-day operating window.",
        "riskLevel": "high" if top_employee.get("count", 0) >= 3 or cash_adjustments else "medium",
        "riskScore": 84 if top_employee.get("count", 0) >= 3 or cash_adjustments else 61,
        "findings": [
            {
                "id": "repeat-manager-pattern",
                "category": "Manager approval review",
                "title": "Paidout activity is concentrated by employee",
                "severity": "high" if top_employee.get("count", 0) >= 3 else "medium",
                "evidence": [
                    f"{top_employee['employee']} is associated with {top_employee.get('count', 0)} paidout(s) totaling ${top_employee.get('total', 0):,.2f}.",
                    f"Cash adjustment count in comparison window: {cash_adjustments}.",
                ],
                "explanation": "Repeated paidout ownership does not establish misconduct, but it is a control review trigger when paired with cash adjustments or margin pressure.",
                "recommendation": "Review receipt attachments, close-out notes, and approval timestamps for the employee's paidouts; require second approval for cash adjustments.",
            },
            {
                "id": "recurring-inventory-pressure",
                "category": "Inventory controls",
                "title": "Recurring shortages require usage variance review",
                "severity": "high" if len(shortages) >= 4 else "medium",
                "evidence": [
                    f"{len(shortages)} item(s) remain below reorder level in the comparison window.",
                    "Chicken and oil shortages should be compared against sales mix and prep logs.",
                ],
                "explanation": "Repeated shortage patterns can indicate waste, over-portioning, unrecorded transfers, or emergency purchasing behavior.",
                "recommendation": "Run a blind count on high-cost proteins and fryer oil, then compare actual usage to item-level POS sales.",
            },
        ],
        "nextActions": [
            "Pull register close records for the same timestamps.",
            "Spot-count chicken and oil before the next delivery.",
            "Create a paidout rule: cash adjustments over $100 require owner approval.",
        ],
    }


def _call_gemini(data, question):
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        return None
    model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = {
        "system": SYSTEM_PROMPT,
        "question": question,
        "requiredOutputShape": {
            "summary": "string",
            "riskLevel": "low | medium | high",
            "riskScore": "0-100",
            "findings": [{"category": "string", "title": "string", "severity": "low | medium | high", "evidence": ["string"], "explanation": "string", "recommendation": "string"}],
            "nextActions": ["string"],
        },
        "languageRules": [
            "Write for restaurant owners and operators, not engineers.",
            "Do not include JSON paths, object names, IDs, booleans, snake_case keys, or raw field paths in evidence.",
            "Convert evidence into plain sentences such as '$620 cash adjustment by Sam Patel using cash'.",
            "Use clear business wording for paidouts, inventory shortages, cash control, approval review, and reconciliation.",
        ],
        "restaurantData": data,
    }
    body = {
        "contents": [{"parts": [{"text": json.dumps(prompt, default=str)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    text = raw.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    try:
        parsed = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        try:
            parsed = json.loads(match.group(0)) if match else None
        except ValueError:
            logger.warning("Gemini returned malformed JSON; using rule-based audit fallback")
            return None
    if isinstance(parsed, dict):
        parsed["_source"] = "gemini"
    return parsed


def mirror_report_to_mongo(ai_report, data, audit_type="operational_audit"):
    report = ai_report.report or {}
    document = {
        "djangoReportId": ai_report.id,
        "storeId": str(ai_report.store_id),
        "storeName": ai_report.store.name,
        "clientName": ai_report.store.client.name,
        "dateRange": ai_report.date_range,
        "auditPeriod": {"startDate": data.get("startDate"), "endDate": data.get("endDate")},
        "question": ai_report.question,
        "riskLevel": report.get("riskLevel"),
        "riskScore": report.get("riskScore"),
        "summary": report.get("summary"),
        "findings": report.get("findings", []),
        "nextActions": report.get("nextActions", []),
        "source": ai_report.source,
        "auditType": audit_type,
        "generatedAt": ai_report.created_at,
        "createdAt": ai_report.created_at,
        "operationalContext": data,
    }
    mongo_id = insert_document(AI_REPORTS, document)
    if mongo_id:
        logger.info("Saved AI report %s to MongoDB aiReports as %s", ai_report.id, mongo_id)
    return mongo_id


def mirror_investigation_to_mongo(ai_report, data, finding_id=None, context=""):
    report = ai_report.report or {}
    historical = data.get("historicalPatterns", {})
    document = {
        "djangoReportId": ai_report.id,
        "storeId": str(ai_report.store_id),
        "storeName": ai_report.store.name,
        "clientName": ai_report.store.client.name,
        "investigationType": "risk_pattern_investigation",
        "findingId": finding_id or "selected finding",
        "context": context,
        "comparedPeriods": {
            "startDate": data.get("startDate"),
            "endDate": data.get("endDate"),
            "comparisonWindow": "prior seven days",
        },
        "riskLevel": report.get("riskLevel"),
        "riskScore": report.get("riskScore"),
        "summary": report.get("summary"),
        "findings": report.get("findings", []),
        "nextActions": report.get("nextActions", []),
        "repeatedAnomalies": data.get("heuristics", []),
        "employeePatterns": historical.get("paidoutsByEmployee", []),
        "inventoryPressure": historical.get("repeatedInventoryShortages", []),
        "cashAdjustmentCount": historical.get("cashAdjustmentCount", 0),
        "source": ai_report.source,
        "generatedAt": ai_report.created_at,
        "createdAt": ai_report.created_at,
        "operationalContext": data,
    }
    mongo_id = insert_document(INVESTIGATION_REPORTS, document)
    if mongo_id:
        logger.info("Saved investigation report %s to MongoDB investigationReports as %s", ai_report.id, mongo_id)
    return mongo_id


def _get_store(user, store_id=None):
    qs = accessible_stores(user)
    if store_id:
        return qs.get(pk=store_id)
    return qs.first()


def _source_label(source):
    return "Gemini operational analysis" if source == "gemini" else "Rule-based audit review"


def _mongodb_status_label():
    ok, _ = ping_mongodb()
    return "MongoDB Connected" if ok else "MongoDB Unavailable"


def clean_report_for_display(report):
    if not isinstance(report, dict):
        return {}
    cleaned = {
        "summary": _clean_text(report.get("summary", "")),
        "riskLevel": str(report.get("riskLevel", "medium")).lower(),
        "riskScore": report.get("riskScore", 0),
        "findings": [],
        "nextActions": [_clean_text(item) for item in report.get("nextActions", []) if item],
    }
    for finding in report.get("findings", []) or []:
        if not isinstance(finding, dict):
            continue
        cleaned["findings"].append({
            "category": _clean_text(finding.get("category", "Operational risk")),
            "title": _clean_text(finding.get("title", "Operational finding")),
            "severity": str(finding.get("severity", "medium")).lower(),
            "evidence": [_clean_evidence(item) for item in finding.get("evidence", []) if item],
            "explanation": _clean_text(finding.get("explanation", "")),
            "recommendation": _clean_text(finding.get("recommendation", "")),
        })
    return cleaned


def _clean_evidence(value):
    text = _clean_text(value)
    paidout_match = re.search(
        r"paidouts\[id=\d+,\s*amount=([\d.]+),\s*reason='([^']+)',\s*employee='([^']+)',\s*paymentMethod='([^']+)'",
        text,
    )
    if paidout_match:
        amount, reason, employee, method = paidout_match.groups()
        return f"${float(amount):,.2f} {reason} recorded by {employee} using {method}."

    employee_match = re.search(r"paidoutsByEmployee:\s*\{'employee': '([^']+)', 'total': ([\d.]+), 'count': (\d+)\}", text)
    if employee_match:
        employee, total, count = employee_match.groups()
        return f"{employee} recorded {count} paidout(s) totaling ${float(total):,.2f} in the comparison period."

    ratio_match = re.search(r"paidoutToSalesRatio:\s*([\d.]+)", text)
    if ratio_match:
        return f"Paidouts equal {float(ratio_match.group(1)) * 100:.1f}% of sales for the audit period."

    low_stock_match = re.search(r"lowStock:\s*(.*)", text)
    if low_stock_match:
        return low_stock_match.group(1).strip().rstrip(".") + "."

    if "historicalPatterns.repeatedInventoryShortages" in text:
        return "Repeated low-stock items appear in the seven-day comparison period."

    text = re.sub(r"restaurantData\.", "", text)
    text = re.sub(r"\bid=\d+,?\s*", "", text)
    text = text.replace("suspicious=true", "requires review")
    text = text.replace("suspicious=false", "not automatically flagged")
    text = text.replace("paymentMethod", "payment method")
    text = text.replace("profitLoss", "profit and loss")
    text = text.replace("historicalPatterns", "historical patterns")
    text = text.replace("paidoutsByEmployee", "paidouts by employee")
    text = text.replace("paidoutToSalesRatio", "paidout-to-sales ratio")
    return text


def _clean_text(value):
    text = str(value or "").strip()
    replacements = {
        "paidout-to-sales": "paidout-to-sales",
        "paidouts": "paidouts",
        "cash adjustment": "cash adjustment",
        "_": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text)
    return text


def _period_label(data):
    start = data.get("startDate")
    end = data.get("endDate")
    if start == end:
        return start
    return f"{start} to {end}"


def _kpi_trends(data):
    sales_by_day = list(data.get("historicalPatterns", {}).get("salesByDay", {}).values())
    paidouts_by_day = list(data.get("historicalPatterns", {}).get("paidoutsByDay", {}).values())
    sales_trend = _trend_label(data["salesSummary"]["totalSales"], _prior_average(sales_by_day))
    paidout_trend = _trend_label(data["profitLoss"]["paidouts"], _prior_average(paidouts_by_day), inverse=True)
    ratio_value = data["profitLoss"]["paidoutToSalesRatio"] * 100
    inventory_pressure = len(data.get("lowStock", []))
    return {
        "sales": sales_trend or "Stable",
        "paidouts": paidout_trend or "Watch",
        "paidout_ratio": "Elevated" if ratio_value >= 12 else "Controlled",
        "inventory": "Pressure" if inventory_pressure else "In range",
        "low_stock": f"{inventory_pressure} flagged",
        "profit": "Margin risk" if ratio_value >= 12 or inventory_pressure >= 4 else "On plan",
    }


def _prior_average(values):
    if len(values) <= 1:
        return 0
    prior = values[:-1]
    return sum(prior) / len(prior) if prior else 0


def _trend_label(current, prior, inverse=False):
    if not prior:
        return ""
    change = ((current - prior) / prior) * 100
    if abs(change) < 0.5:
        return "Stable"
    direction = "Down" if change < 0 else "Up"
    value = f"{direction} {abs(change):.1f}%"
    if inverse and change > 0:
        return f"{value} review"
    if inverse and change < 0:
        return f"{value} better"
    return value


def _paidout_row(paidout):
    amount = _num(paidout.amount)
    suspicious = (
        amount >= 250
        or "cash adjustment" in paidout.description.lower()
        or (paidout.payment_source == "cash" and amount >= 150)
    )
    return {
        "id": paidout.id,
        "amount": amount,
        "reason": paidout.description,
        "category": paidout.get_category_display(),
        "employee": paidout.created_by.get_full_name() or paidout.created_by.username,
        "store": paidout.store.name,
        "timestamp": paidout.created_at.isoformat(),
        "paymentMethod": paidout.payment_source,
        "suspicious": suspicious,
    }


def _inventory_row(item):
    current = _num(item.current_quantity)
    reorder = _num(item.low_stock_level)
    cost = _num(item.average_cost or item.cost_per_unit)
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category or "Uncategorized",
        "currentStock": current,
        "unit": item.inventory_unit,
        "dailyUsageEstimate": round(max(reorder / 3, 1), 2) if reorder else 1,
        "reorderLevel": reorder,
        "costPerUnit": cost,
        "inventoryValue": round(current * cost, 2),
        "isLowStock": reorder > 0 and current <= reorder,
    }


def _num(value):
    return float(Decimal(str(value or 0)))
