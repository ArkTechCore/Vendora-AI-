from django import forms
from django.utils import timezone

from inventory.models import InventoryCount
from stores.models import Store


class ReportExportForm(forms.Form):
    REPORT_CHOICES = [
        ("full", "Full mixed report"),
        ("sales", "Sales summary"),
        ("paidouts", "Paid-outs"),
        ("daily_close", "Daily close"),
        ("inventory", "Inventory and low stock"),
        ("purchases", "Purchases"),
        ("platform", "Platform report"),
    ]

    report_type = forms.ChoiceField(choices=REPORT_CHOICES, initial="full")
    store = forms.ModelChoiceField(queryset=Store.objects.none(), required=False)
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["end_date"].initial = timezone.localdate()

        stores = Store.objects.filter(is_active=True)
        if user and user.is_client_owner():
            stores = stores.filter(client=user.client)
            self.fields["report_type"].choices = [choice for choice in self.REPORT_CHOICES if choice[0] != "platform"]
        elif user and user.is_manager():
            stores = stores.filter(pk=user.store_id)
            self.fields["store"].initial = user.store
            self.fields["store"].disabled = True
            self.fields["report_type"].choices = [choice for choice in self.REPORT_CHOICES if choice[0] != "platform"]
        elif user and user.is_super_admin():
            self.fields["report_type"].choices = [("platform", "Platform report")]
            self.fields["report_type"].initial = "platform"
            self.fields["store"].disabled = True
            self.fields["store"].help_text = "Super Admin reports are platform-safe only."
        self.fields["store"].queryset = stores

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and start > end:
            raise forms.ValidationError("Start date cannot be after end date.")
        if self.user and self.user.is_manager():
            cleaned["store"] = self.user.store
        return cleaned


class ActualVsTheoreticalForm(forms.Form):
    store = forms.ModelChoiceField(queryset=Store.objects.none())
    start_count = forms.ModelChoiceField(queryset=InventoryCount.objects.none(), required=False)
    end_count = forms.ModelChoiceField(queryset=InventoryCount.objects.none(), required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        store_qs = Store.objects.filter(is_active=True)
        if user and user.is_client_owner():
            store_qs = store_qs.filter(client=user.client)
        elif user and user.is_manager():
            store_qs = store_qs.filter(pk=user.store_id)
            self.fields["store"].initial = user.store
            self.fields["store"].disabled = True
        self.fields["store"].queryset = store_qs

        store = None
        data = args[0] if args else None
        store_id = data.get("store") if data else None
        if user and user.is_manager():
            store = user.store
        elif store_id:
            store = store_qs.filter(pk=store_id).first()
        elif store_qs.count() == 1:
            store = store_qs.first()

        count_qs = InventoryCount.objects.filter(status=InventoryCount.CLOSED)
        if store:
            count_qs = count_qs.filter(store=store)
        elif user and user.is_client_owner():
            count_qs = count_qs.filter(store__client=user.client)
        self.fields["start_count"].queryset = count_qs.order_by("-business_date")
        self.fields["end_count"].queryset = count_qs.order_by("-business_date")
