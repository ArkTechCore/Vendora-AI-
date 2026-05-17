from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

class PaidOut(models.Model):
    CATEGORY_CHOICES = [
        ('groceries', 'Groceries'), ('meat', 'Meat'), ('vegetables', 'Vegetables'),
        ('cleaning', 'Cleaning'), ('maintenance', 'Maintenance'), ('gas', 'Gas'),
        ('utilities', 'Utilities'), ('refund', 'Refund'), ('other', 'Other'),
        ('emergency_purchase', 'Emergency Purchase'),
    ]
    SOURCE_CHOICES = [('cash', 'Cash'), ('card', 'Card'), ('bank', 'Bank')]

    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='paidouts')
    business_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    description = models.TextField()
    vendor_payee = models.CharField(max_length=160, blank=True)
    payment_source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    receipt_number = models.CharField(max_length=80, blank=True)
    receipt_image = models.ImageField(upload_to='receipts/', null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='paidouts')
    approved = models.BooleanField(default=True)
    locked = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Amount must be greater than 0.")
        if not self.description.strip():
            raise ValidationError("Description is required.")
        duplicate = PaidOut.objects.filter(
            store=self.store,
            amount=self.amount,
            category=self.category,
            payment_source=self.payment_source,
            created_at__date=timezone.localdate(),
        )
        if self.pk:
            duplicate = duplicate.exclude(pk=self.pk)
        if duplicate.exists():
            raise ValidationError("A similar paid-out already exists today. Check before creating a duplicate.")

    def save(self, *args, **kwargs):
        if self.pk and self.locked:
            raise ValidationError("Paid-outs are locked after creation.")
        self.approved = True
        self.locked = True
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.store} {self.amount} {self.category}"
