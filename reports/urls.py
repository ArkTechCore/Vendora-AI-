from django.urls import path

from .views import actual_vs_theoretical, report_pdf, reports_dashboard

urlpatterns = [
    path("", reports_dashboard, name="reports_dashboard"),
    path("pdf/", report_pdf, name="report_pdf"),
    path("actual-vs-theoretical/", actual_vs_theoretical, name="actual_vs_theoretical"),
]
