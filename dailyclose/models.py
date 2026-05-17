from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

class DailyClose(models.Model):
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='daily_closes')
    business_date = models.DateField()
    opening_cash = models.DecimalField(max_digits=10, decimal_places=2)
    cash_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    card_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cash_paidouts = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_cash = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    counted_cash = models.DecimalField(max_digits=10, decimal_places=2)
    short_over = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='daily_closes')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='created_daily_closes')
    locked = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        unique_together = ("store", "business_date")
        ordering = ["-business_date"]

    def save(self, *args, **kwargs):
        if self.pk and self.locked:
            raise ValidationError("Daily close records are locked after creation.")
        self.expected_cash = self.opening_cash + self.cash_sales - self.cash_paidouts
        self.short_over = self.counted_cash - self.expected_cash
        self.locked = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.store} close {self.business_date}"
