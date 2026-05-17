import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from reports.pdf import SimplePDF
from .services import analyze_operations, dashboard_context, investigate_finding
from .services import clean_report_for_display
from .services import default_store_for
from .services import accessible_stores
from .models import AIReport


@login_required
@ensure_csrf_cookie
def auditor_dashboard(request):
    context = dashboard_context(request.user, store_id=request.GET.get("store"))
    return render(request, "ai_auditor/dashboard.html", context)


@login_required
@require_POST
def run_audit(request):
    store_id = request.POST.get("storeId")
    analyze_operations(
        request.user,
        store_id=store_id,
        date_range="yesterday",
        question="Run operational audit for the current audit period",
    )
    messages.success(request, "Operational audit completed.")
    return redirect(_auditor_url(store_id))


@login_required
@require_POST
def run_investigation(request):
    store_id = request.POST.get("storeId")
    investigate_finding(
        request.user,
        store_id=store_id,
        finding_id="paidout-cash-adjustment",
        context=request.POST.get("context", "Investigate current operational risk pattern."),
    )
    messages.success(request, "Risk pattern investigation completed.")
    return redirect(_auditor_url(store_id))


@login_required
@require_POST
def analyze_api(request):
    payload = _json_payload(request)
    result = analyze_operations(
        request.user,
        store_id=payload.get("storeId"),
        date_range=payload.get("dateRange", "yesterday"),
        question=payload.get("question", "Analyze yesterday's operations"),
    )
    return JsonResponse(result)


@login_required
@require_POST
def investigate_api(request):
    payload = _json_payload(request)
    result = investigate_finding(
        request.user,
        store_id=payload.get("storeId"),
        finding_id=payload.get("findingId"),
        context=payload.get("context", ""),
    )
    return JsonResponse(result)


@login_required
def report_pdf(request):
    store = default_store_for(request.user)
    store_id = request.GET.get("storeId")
    if store_id:
        store = accessible_stores(request.user).filter(pk=store_id).first()
    if not store:
        raise Http404("Store not found")
    ai_report = AIReport.objects.filter(store=store).first()
    if not ai_report:
        raise Http404("No AI audit report found")

    report = clean_report_for_display(ai_report.report)
    pdf = _build_ai_report_pdf(store, ai_report, report)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="vendora-ai-audit-{store.code or store.id}.pdf"'
    return response


def _json_payload(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return {}


def _auditor_url(store_id):
    url = reverse("ai_auditor")
    return f"{url}?store={store_id}" if store_id else url


def _build_ai_report_pdf(store, ai_report, report):
    doc = SimplePDF("Vendora AI Restaurant Auditor")
    doc.add_report_title("AI Restaurant Operations Audit", [
        ("Store", store.name),
        ("Generated", ai_report.created_at.strftime("%Y-%m-%d %H:%M UTC")),
        ("Source", "Gemini" if ai_report.source == "gemini" else "Rule-based audit"),
    ])
    doc.add_summary_grid([
        ("Risk Level", str(report.get("riskLevel", "medium")).title()),
        ("Risk Score", f"{report.get('riskScore', 0)}/100"),
        ("Audit Period", ai_report.date_range.title()),
        ("Report ID", ai_report.id),
    ])

    doc.add_section("Executive Summary")
    _add_paragraph(doc, report.get("summary", "No summary available."))

    doc.add_section("Key Findings")
    findings = report.get("findings", []) or []
    if not findings:
        _add_paragraph(doc, "No material findings were returned for this audit.")
    for index, finding in enumerate(findings, start=1):
        _add_heading(doc, f"{index}. {finding.get('title', 'Operational finding')}")
        _add_meta_line(doc, "Severity", str(finding.get("severity", "medium")).title())
        _add_meta_line(doc, "Category", finding.get("category", "Operational risk"))
        _add_paragraph(doc, finding.get("explanation", ""))
        _add_heading(doc, "Evidence", size=10)
        for item in finding.get("evidence", []) or []:
            _add_bullet(doc, item)
        _add_heading(doc, "Recommendation", size=10)
        _add_paragraph(doc, finding.get("recommendation", ""))
        doc.y -= 8

    doc.add_section("Next Actions")
    for item in report.get("nextActions", []) or []:
        _add_bullet(doc, item)
    doc.add_footer("Generated by Vendora AI Restaurant Auditor.")
    return doc.render()


def _add_heading(doc, text, size=11):
    doc._ensure_space(24)
    doc.text(text, y=doc.y, size=size, bold=True, color=(0.06, 0.09, 0.16))
    doc.y -= 16


def _add_meta_line(doc, label, value):
    doc._ensure_space(18)
    doc.text(f"{label.upper()}: ", y=doc.y, size=9, bold=True, color=(0.29, 0.33, 0.38))
    doc.text(value, x=110, y=doc.y, size=9)
    doc.y -= 14


def _add_paragraph(doc, text):
    for line in _wrap_pdf_text(text, width=92):
        doc._ensure_space(16)
        doc.text(line, y=doc.y, size=9)
        doc.y -= 13
    doc.y -= 4


def _add_bullet(doc, text):
    for index, line in enumerate(_wrap_pdf_text(text, width=88)):
        doc._ensure_space(16)
        prefix = "- " if index == 0 else "  "
        doc.text(prefix + line, y=doc.y, size=9)
        doc.y -= 13
    doc.y -= 2


def _wrap_pdf_text(text, width=88):
    words = str(text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word[:width]
    if current:
        lines.append(current)
    return lines or [""]
