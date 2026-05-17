from decimal import Decimal
from decimal import ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from simple_history.models import HistoricalRecords

class Vendor(models.Model):
    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='vendors')
    name = models.CharField(max_length=160)
    contact_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    UNIT_CHOICES = [
        ('g', 'g'), ('kg', 'kg'), ('ml', 'ml'), ('l', 'l'), ('pcs', 'pcs'), ('piece', 'piece'),
        ('lb', 'lb'), ('oz', 'oz'), ('gal', 'gal'), ('qt', 'qt'), ('bag', 'bag'), ('case', 'case'),
        ('box', 'box'), ('jug', 'jug'), ('tub', 'tub'), ('gallon', 'gallon'),
    ]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='ingredients')
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, null=True, blank=True, related_name='ingredients')
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='ingredients')
    category = models.CharField(max_length=80, blank=True)
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='lb')
    purchase_unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='case')
    inventory_unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='lb')
    recipe_unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='lb')
    purchase_to_inventory_factor = models.DecimalField(max_digits=12, decimal_places=4, default=1)
    inventory_to_recipe_factor = models.DecimalField(max_digits=12, decimal_places=4, default=1)
    current_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    low_stock_level = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    average_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    last_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    @property
    def value_estimate(self):
        return self.current_quantity * self.average_cost

    @property
    def cost_per_recipe_unit(self):
        if not self.inventory_to_recipe_factor:
            return self.average_cost
        return self.average_cost / self.inventory_to_recipe_factor

    def save(self, *args, **kwargs):
        self.unit = self.inventory_unit
        if not self.average_cost and self.cost_per_unit:
            self.average_cost = self.cost_per_unit
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='menu_items')
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, null=True, blank=True, related_name='menu_items')
    category = models.CharField(max_length=80, blank=True)
    name = models.CharField(max_length=160)
    external_pos_name = models.CharField(max_length=160, blank=True)
    external_pos_id = models.CharField(max_length=120, blank=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    target_food_cost_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()

    @property
    def recipe_cost(self):
        return sum((item.calculated_cost for item in self.recipe_items.select_related("ingredient").all()), Decimal("0"))

    @property
    def estimated_profit(self):
        return Decimal(str(self.selling_price or 0)) - self.recipe_cost

    @property
    def food_cost_percent(self):
        selling_price = Decimal(str(self.selling_price or 0))
        if not selling_price:
            return 0
        return (self.recipe_cost / selling_price) * 100

    @property
    def recipe_status(self):
        return "Mapped" if self.recipe_items.exists() else "Needs recipe"

    @property
    def margin_status(self):
        percent = self.food_cost_percent
        if percent <= self.target_food_cost_percentage:
            return "Good"
        if percent <= self.target_food_cost_percentage + Decimal("7"):
            return "Watch"
        return "Bad"

    def __str__(self):
        return self.name


class RecipeIngredient(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='recipe_items')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='recipe_usages')
    quantity_used = models.DecimalField(max_digits=12, decimal_places=3)
    recipe_unit = models.CharField(max_length=20, choices=Ingredient.UNIT_CHOICES, default='lb')

    @property
    def calculated_cost(self):
        return self.quantity_used * self.ingredient.cost_per_recipe_unit

    class Meta:
        unique_together = ("menu_item", "ingredient")

    def __str__(self):
        return f"{self.menu_item} uses {self.quantity_used} {self.ingredient.unit} {self.ingredient}"


class StockMovement(models.Model):
    RECEIVE = 'receive'
    USAGE = 'usage'
    WASTE = 'waste'
    ADJUSTMENT = 'adjustment'
    POS_DEDUCTION = 'pos_deduction'
    THEORETICAL = 'theoretical'
    MOVEMENT_CHOICES = [
        (RECEIVE, 'Receive'),
        (USAGE, 'Usage'),
        (WASTE, 'Waste'),
        (ADJUSTMENT, 'Adjustment'),
        (POS_DEDUCTION, 'POS Deduction'),
        (THEORETICAL, 'Theoretical Usage'),
    ]

    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=32, choices=MOVEMENT_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='stock_movements')
    created_at = models.DateTimeField(auto_now_add=True)
    source_sale_id = models.CharField(max_length=120, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("Quantity must be greater than 0.")

    def save(self, *args, **kwargs):
        self.quantity = Decimal(str(self.quantity)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        self.full_clean()
        if self.pk:
            raise ValidationError("Stock movements are locked after creation.")
        with transaction.atomic():
            ingredient = Ingredient.objects.select_for_update().get(pk=self.ingredient_id)
            if self.movement_type == self.RECEIVE:
                ingredient.current_quantity += self.quantity
            elif self.movement_type in {self.USAGE, self.WASTE, self.POS_DEDUCTION}:
                ingredient.current_quantity -= self.quantity
            elif self.movement_type == self.ADJUSTMENT:
                ingredient.current_quantity = self.quantity
            ingredient.save(update_fields=["current_quantity"])
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} {self.ingredient}"


class InventoryCount(models.Model):
    DRAFT = 'draft'
    CLOSED = 'closed'
    STATUS_CHOICES = [(DRAFT, 'Draft'), (CLOSED, 'Closed')]

    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='inventory_counts')
    business_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    counted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='inventory_counts')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        unique_together = ("store", "business_date")
        ordering = ["-business_date", "-created_at"]

    @property
    def is_closed(self):
        return self.status == self.CLOSED

    def __str__(self):
        return f"{self.store} count {self.business_date}"


class InventoryCountItem(models.Model):
    count = models.ForeignKey(InventoryCount, on_delete=models.CASCADE, related_name='items')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name='count_items')
    counted_quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost_snapshot = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    class Meta:
        unique_together = ("count", "ingredient")
        ordering = ["ingredient__name"]

    @property
    def counted_value(self):
        return self.counted_quantity * self.unit_cost_snapshot

    def save(self, *args, **kwargs):
        if not self.unit_cost_snapshot:
            self.unit_cost_snapshot = self.ingredient.cost_per_unit
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ingredient} counted {self.counted_quantity}"


class PurchaseReceive(models.Model):
    DRAFT = 'draft'
    POSTED = 'posted'
    VOID = 'void'
    STATUS_CHOICES = [(DRAFT, 'Draft'), (POSTED, 'Posted'), (VOID, 'Void')]

    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='purchase_receives')
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_receives')
    invoice_number = models.CharField(max_length=120, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=POSTED)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    invoice_file = models.FileField(upload_to='vendor_invoices/', null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_receives')
    received_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.invoice_number or f"Receive {self.id}"


class PurchaseReceiveItem(models.Model):
    purchase = models.ForeignKey(PurchaseReceive, on_delete=models.CASCADE, related_name='items')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name='purchase_items')
    vendor_item_name = models.CharField(max_length=160, blank=True)
    pack_size = models.CharField(max_length=80, blank=True)
    purchase_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    purchase_unit = models.CharField(max_length=20, choices=Ingredient.UNIT_CHOICES, blank=True)
    quantity_received = models.DecimalField(max_digits=12, decimal_places=3)
    inventory_unit = models.CharField(max_length=20, choices=Ingredient.UNIT_CHOICES, blank=True)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        creating = self.pk is None
        self.quantity_received = Decimal(str(self.quantity_received)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        self.unit_cost = Decimal(str(self.unit_cost or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if not self.total_cost:
            self.total_cost = (self.quantity_received * self.unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)
        if creating:
            if self.unit_cost:
                old_qty = Decimal(str(self.ingredient.current_quantity or 0))
                old_avg = Decimal(str(self.ingredient.average_cost or self.ingredient.cost_per_unit or 0))
                new_qty = Decimal(str(self.quantity_received or 0))
                weighted_qty = old_qty + new_qty
                self.ingredient.last_cost = self.unit_cost
                self.ingredient.cost_per_unit = self.unit_cost
                if weighted_qty > 0:
                    self.ingredient.average_cost = (((old_qty * old_avg) + (new_qty * self.unit_cost)) / weighted_qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                self.ingredient.save(update_fields=["cost_per_unit", "average_cost", "last_cost"])
            StockMovement.objects.create(
                ingredient=self.ingredient,
                movement_type=StockMovement.RECEIVE,
                quantity=self.quantity_received,
                note=f"Purchase receive {self.purchase}",
                created_by=self.purchase.received_by,
            )

    def __str__(self):
        return f"{self.quantity_received} {self.ingredient}"
