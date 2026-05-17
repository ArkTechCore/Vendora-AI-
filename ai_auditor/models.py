from django.db import models


class AIReport(models.Model):
    store = models.ForeignKey("stores.Store", on_delete=models.CASCADE, related_name="ai_reports")
    date_range = models.CharField(max_length=32, default="yesterday")
    question = models.TextField(blank=True)
    report = models.JSONField(default=dict)
    source = models.CharField(max_length=32, default="gemini")
    mongo_document_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.store} AI audit {self.created_at:%Y-%m-%d %H:%M}"
