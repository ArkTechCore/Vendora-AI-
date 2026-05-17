from django.db import models
from simple_history.models import HistoricalRecords

class Store(models.Model):
    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='stores')
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=40)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        unique_together = ("client", "code")
        ordering = ["client__name", "name"]

    def __str__(self):
        return f"{self.client} - {self.name}"
