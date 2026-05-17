from django.urls import path

from . import views

urlpatterns = [
    path("", views.auditor_dashboard, name="ai_auditor"),
    path("run-audit", views.run_audit, name="ai_run_audit"),
    path("run-investigation", views.run_investigation, name="ai_run_investigation"),
    path("report.pdf", views.report_pdf, name="ai_report_pdf"),
    path("api/ai/analyze", views.analyze_api, name="ai_analyze"),
    path("api/ai/investigate", views.investigate_api, name="ai_investigate"),
]
