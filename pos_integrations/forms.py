from django import forms
from django.utils import timezone

from inventory.models import MenuItem
from .models import ImportedSale, ImportedSaleItem, POSConnection


class POSConnectionForm(forms.ModelForm):
    current_password = forms.CharField(
        label="Confirm your password to save POS API settings",
        widget=forms.PasswordInput(),
        required=True,
        help_text="Required whenever POS credentials are added or changed.",
    )

    class Meta:
        model = POSConnection
        fields = (
            "client", "store", "provider", "connection_name", "environment",
            "external_merchant_id", "external_location_id",
            "api_client_id", "client_secret", "access_token", "refresh_token",
            "token_expires_at", "webhook_secret", "scopes",
            "auto_sync_enabled", "is_active",
        )
        widgets = {
            "client_secret": forms.PasswordInput(render_value=False, attrs={"placeholder": "Hidden after save"}),
            "access_token": forms.PasswordInput(render_value=False, attrs={"placeholder": "Paste POS API key, then it will be hidden"}),
            "refresh_token": forms.PasswordInput(render_value=False, attrs={"placeholder": "Hidden after save"}),
            "webhook_secret": forms.PasswordInput(render_value=False, attrs={"placeholder": "Hidden after save"}),
            "token_expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "scopes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "access_token": "POS API key",
            "api_client_id": "POS client ID",
            "external_merchant_id": "Merchant ID",
            "external_location_id": "Location ID",
            "auto_sync_enabled": "Auto-sync when API is live",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_user = user
        if user and user.is_client_owner():
            self.fields["client"].initial = user.client
            self.fields["client"].disabled = True
            self.fields["store"].queryset = user.client.stores.filter(is_active=True)
        elif user and user.is_manager():
            self.fields["client"].initial = user.client
            self.fields["client"].disabled = True
            self.fields["store"].initial = user.store
            self.fields["store"].disabled = True
            self.fields["store"].queryset = user.client.stores.filter(pk=user.store_id)
        for field in ("client_secret", "access_token", "refresh_token", "webhook_secret"):
            self.fields[field].required = False
            if self.instance and self.instance.pk and getattr(self.instance, field):
                self.fields[field].help_text = "Saved and hidden. Leave blank to keep existing value."

    def clean_current_password(self):
        password = self.cleaned_data.get("current_password")
        if self.request_user and not self.request_user.check_password(password):
            raise forms.ValidationError("Password did not match your login.")
        return password

    def save(self, commit=True):
        previous = None
        if self.instance and self.instance.pk:
            previous = POSConnection.objects.get(pk=self.instance.pk)
        connection = super().save(commit=False)
        if self.request_user and self.request_user.is_manager():
            connection.client = self.request_user.client
            connection.store = self.request_user.store
        elif self.request_user and self.request_user.is_client_owner():
            connection.client = self.request_user.client
        if previous:
            for field in ("client_secret", "access_token", "refresh_token", "webhook_secret"):
                if not self.cleaned_data.get(field):
                    setattr(connection, field, getattr(previous, field))
        if commit:
            connection.save()
            self.save_m2m()
        return connection


class ImportedSaleForm(forms.ModelForm):
    class Meta:
        model = ImportedSale
        fields = ("connection", "external_order_id", "business_date", "total_amount", "cash_amount", "card_amount", "tax_amount", "tip_amount", "discount_amount")
        widgets = {"business_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user.is_super_admin():
            qs = POSConnection.objects.filter(client=user.client)
            if user.is_manager():
                qs = qs.filter(store=user.store)
            self.fields["connection"].queryset = qs


class ImportedSaleItemForm(forms.ModelForm):
    class Meta:
        model = ImportedSaleItem
        fields = ("sale", "external_item_id", "item_name", "quantity", "unit_price", "mapped_menu_item")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user.is_super_admin():
            sales = ImportedSale.objects.filter(connection__client=user.client)
            items = MenuItem.objects.filter(client=user.client, is_active=True)
            if user.is_manager():
                sales = sales.filter(connection__store=user.store)
                items = items.filter(store__in=[user.store, None])
            self.fields["sale"].queryset = sales
            self.fields["mapped_menu_item"].queryset = items


class ManualSalesEntryForm(forms.Form):
    store = forms.ModelChoiceField(queryset=None)
    business_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), initial=timezone.localdate)
    cash_amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, initial=0)
    card_amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, initial=0)
    tax_amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, initial=0, required=False)
    tip_amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, initial=0, required=False)
    discount_amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, initial=0, required=False)
    custom_sales_amount = forms.DecimalField(
        label="Custom / unmapped sales",
        max_digits=10,
        decimal_places=2,
        min_value=0,
        initial=0,
        required=False,
        help_text="Use for sales not mapped to saved menu items yet.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        from stores.models import Store

        stores = Store.objects.filter(is_active=True)
        if user and user.is_client_owner():
            stores = stores.filter(client=user.client)
        elif user and user.is_manager():
            stores = stores.filter(pk=user.store_id)
            self.fields["store"].initial = user.store
            self.fields["store"].disabled = True
        self.fields["store"].queryset = stores

    def clean(self):
        cleaned = super().clean()
        if self.user and self.user.is_manager():
            cleaned["store"] = self.user.store
        return cleaned
