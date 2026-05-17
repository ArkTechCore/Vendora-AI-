from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import Ingredient, MenuItem, PurchaseReceive, PurchaseReceiveItem, RecipeIngredient, StockMovement, Vendor


class TenantFormMixin:
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user and not user.is_super_admin():
            for field in ("client",):
                if field in self.fields:
                    self.fields[field].initial = user.client
                    self.fields[field].disabled = True
            if "store" in self.fields:
                if user.is_manager():
                    self.fields["store"].initial = user.store
                    self.fields["store"].disabled = True
                else:
                    self.fields["store"].queryset = user.client.stores.filter(is_active=True)
            if "vendor" in self.fields:
                self.fields["vendor"].queryset = user.client.vendors.filter(is_active=True)
            if "ingredient" in self.fields:
                self.fields["ingredient"].queryset = user.client.ingredients.filter(is_active=True)
            if "menu_item" in self.fields:
                self.fields["menu_item"].queryset = user.client.menu_items.filter(is_active=True)


class VendorForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ("client", "name", "contact_name", "phone", "email", "address", "is_active")


class IngredientForm(TenantFormMixin, forms.ModelForm):
    opening_quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0,
        required=False,
        help_text="Optional for new ingredients. VendoraOps records it as an opening stock adjustment.",
    )

    class Meta:
        model = Ingredient
        fields = (
            "client", "store", "vendor", "category", "name", "purchase_unit", "inventory_unit",
            "recipe_unit", "purchase_to_inventory_factor", "inventory_to_recipe_factor",
            "low_stock_level", "average_cost", "last_cost", "is_active",
        )


class MenuItemForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ("client", "store", "category", "name", "external_pos_name", "external_pos_id", "selling_price", "target_food_cost_percentage", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["external_pos_name"].help_text = "Leave blank when the POS item name matches the VendoraOps menu item name."

    def clean_external_pos_name(self):
        value = self.cleaned_data.get("external_pos_name", "").strip()
        return value or self.cleaned_data.get("name", "")


class RecipeIngredientForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = RecipeIngredient
        fields = ("menu_item", "ingredient", "quantity_used")

    def clean(self):
        cleaned = super().clean()
        menu_item = cleaned.get("menu_item")
        ingredient = cleaned.get("ingredient")
        if menu_item and ingredient and menu_item.client_id != ingredient.client_id:
            raise forms.ValidationError("Recipe ingredient must belong to the same client as the menu item.")
        if menu_item and ingredient and menu_item.store_id and ingredient.store_id and menu_item.store_id != ingredient.store_id:
            raise forms.ValidationError("Store-specific menu items can only use ingredients from the same store.")
        return cleaned


class RecipeMenuItemForm(forms.Form):
    menu_item = forms.ModelChoiceField(queryset=MenuItem.objects.none(), label="Menu item")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user.is_super_admin():
            self.fields["menu_item"].queryset = user.client.menu_items.filter(is_active=True).order_by("name")
        else:
            self.fields["menu_item"].queryset = MenuItem.objects.filter(is_active=True).order_by("client__name", "name")


class BaseRecipeIngredientFormSet(BaseInlineFormSet):
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        ingredient_qs = Ingredient.objects.filter(is_active=True)
        if user and not user.is_super_admin():
            ingredient_qs = ingredient_qs.filter(client=user.client)
        if self.instance and self.instance.store_id:
            ingredient_qs = ingredient_qs.filter(store__in=[self.instance.store, None])
        for form in self.forms:
            form.fields["ingredient"].queryset = ingredient_qs.order_by("name")

    def clean(self):
        super().clean()
        seen = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            ingredient = form.cleaned_data.get("ingredient")
            quantity = form.cleaned_data.get("quantity_used")
            if not ingredient and not quantity:
                continue
            if ingredient is None or quantity is None:
                raise forms.ValidationError("Each recipe row needs both ingredient and quantity.")
            if quantity <= 0:
                raise forms.ValidationError("Recipe quantities must be greater than zero.")
            if ingredient.pk in seen:
                raise forms.ValidationError("Each ingredient can appear only once per recipe.")
            seen.add(ingredient.pk)
            if ingredient.client_id != self.instance.client_id:
                raise forms.ValidationError("Recipe ingredient must belong to the same client as the menu item.")
            if self.instance.store_id and ingredient.store_id and ingredient.store_id != self.instance.store_id:
                raise forms.ValidationError("Store-specific menu items can only use ingredients from the same store.")


RecipeIngredientFormSet = inlineformset_factory(
    MenuItem,
    RecipeIngredient,
    formset=BaseRecipeIngredientFormSet,
    fields=("ingredient", "quantity_used", "recipe_unit"),
    extra=12,
    can_delete=True,
)


class StockMovementForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ("ingredient", "movement_type", "quantity", "note")

    def clean(self):
        cleaned = super().clean()
        movement_type = cleaned.get("movement_type")
        quantity = cleaned.get("quantity")
        if movement_type == StockMovement.ADJUSTMENT and quantity is not None:
            cleaned["note"] = cleaned.get("note") or "Counted stock adjustment"
        return cleaned


class PurchaseReceiveForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = PurchaseReceive
        fields = ("store", "vendor", "invoice_number", "notes")


class PurchaseReceiveItemForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = PurchaseReceiveItem
        fields = ("purchase", "ingredient", "quantity_received", "unit_cost")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        if user and not user.is_super_admin():
            self.fields["purchase"].queryset = PurchaseReceive.objects.filter(store__client=user.client)


class BulkReceiveForm(TenantFormMixin, forms.ModelForm):
    class Meta:
        model = PurchaseReceive
        fields = ("store", "vendor", "invoice_number", "invoice_date", "due_date", "tax_fees", "invoice_file", "notes")
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class StockCountStoreForm(forms.Form):
    store = forms.ModelChoiceField(queryset=None)
    business_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from django.utils import timezone
        self.fields["business_date"].initial = timezone.localdate()
        if user.is_manager():
            self.fields["store"].queryset = user.client.stores.filter(pk=user.store_id)
            self.fields["store"].initial = user.store
            self.fields["store"].disabled = True
        elif user.is_client_owner():
            self.fields["store"].queryset = user.client.stores.filter(is_active=True)
        else:
            from stores.models import Store
            self.fields["store"].queryset = Store.objects.filter(is_active=True)
