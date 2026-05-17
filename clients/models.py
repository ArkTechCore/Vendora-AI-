from django.db import models
from simple_history.models import HistoricalRecords

class Client(models.Model):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    SUSPENDED = 'suspended'
    STATUS_CHOICES = [(ACTIVE, 'Active'), (INACTIVE, 'Inactive'), (SUSPENDED, 'Suspended')]

    name = models.CharField(max_length=160)
    owner_name = models.CharField(max_length=160)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    street_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, default="US")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def full_address(self):
        parts = [
            self.street_address,
            self.city,
            self.state,
            self.postal_code,
            self.country,
        ]
        structured = ", ".join(part for part in parts if part)
        return structured or self.address
