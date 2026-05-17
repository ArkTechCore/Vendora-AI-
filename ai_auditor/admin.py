from django.contrib import admin

from .models import AIReport


@admin.register(AIReport)
class AIReportAdmin(admin.ModelAdmin):
    list_display = ("store", "date_range", "source", "created_at")
    list_filter = ("date_range", "source", "created_at")
    search_fields = ("store__name", "question")
