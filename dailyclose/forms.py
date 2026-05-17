from django import forms

from .models import DailyClose
from .services import calculate_daily_close_totals


class DailyCloseForm(forms.ModelForm):
    class Meta:
        model = DailyClose
        fields = ("store", "business_date", "opening_cash", "counted_cash", "notes")
        widgets = {"business_date": forms.DateInput(attrs={"type": "date"})}
        labels = {
            "opening_cash": "Opening balance",
            "counted_cash": "Ending counter cash",
        }
        help_texts = {
            "opening_cash": "Cash placed in the drawer at the start of the day.",
            "counted_cash": "Cash physically counted in the drawer at day close.",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user and user.is_manager():
            self.fields["store"].initial = user.store
            self.fields["store"].disabled = True
        elif user and user.is_client_owner():
            self.fields["store"].queryset = user.client.stores.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        store = self.user.store if self.user and self.user.is_manager() else cleaned.get("store")
        business_date = cleaned.get("business_date")
        if store and business_date:
            cleaned.update(calculate_daily_close_totals(store, business_date))
        return cleaned
