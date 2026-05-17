from django.db import models
from simple_history.models import HistoricalRecords

class POSConnection(models.Model):
    PROVIDER_CHOICES = [('clover', 'Clover'), ('square', 'Square'), ('toast', 'Toast'), ('csv', 'CSV'), ('other', 'Other')]
    SYNC_STATUS_CHOICES = [('idle', 'Idle'), ('success', 'Success'), ('failed', 'Failed')]
    ENVIRONMENT_CHOICES = [('sandbox', 'Sandbox'), ('production', 'Production')]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='pos_connections')
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='pos_connections')
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    connection_name = models.CharField(max_length=160, blank=True)
    environment = models.CharField(max_length=20, choices=ENVIRONMENT_CHOICES, default='sandbox')
    external_merchant_id = models.CharField(max_length=160, blank=True)
    external_location_id = models.CharField(max_length=160, blank=True)
    api_client_id = models.CharField(max_length=255, blank=True)
    client_secret = models.TextField(blank=True)
    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    webhook_secret = models.TextField(blank=True)
    scopes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    auto_sync_enabled = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(max_length=20, choices=SYNC_STATUS_CHOICES, default='idle')
    last_error = models.TextField(blank=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.store} {self.get_provider_display()}"


class ImportedSale(models.Model):
    connection = models.ForeignKey(POSConnection, on_delete=models.CASCADE, related_name='sales')
    external_order_id = models.CharField(max_length=160)
    business_date = models.DateField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    cash_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    card_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tip_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=30, default='imported')
    processed_inventory = models.BooleanField(default=False)
    processed_theoretical_usage = models.BooleanField(default=False)
    imported_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        unique_together = ("connection", "external_order_id")
        ordering = ["-business_date", "-imported_at"]

    def __str__(self):
        return self.external_order_id


class ImportedSaleItem(models.Model):
    sale = models.ForeignKey(ImportedSale, on_delete=models.CASCADE, related_name='items')
    external_item_id = models.CharField(max_length=160, blank=True)
    item_name = models.CharField(max_length=160)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    mapped_menu_item = models.ForeignKey('inventory.MenuItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='sale_items')

    def __str__(self):
        return f"{self.item_name} x {self.quantity}"
