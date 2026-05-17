from django import forms

from .models import PaidOut


class PaidOutForm(forms.ModelForm):
    class Meta:
        model = PaidOut
        fields = ("store", "business_date", "amount", "category", "vendor_payee", "description", "payment_source", "receipt_number", "receipt_image")
        widgets = {"business_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.is_manager():
            self.fields["store"].initial = user.store
            self.fields["store"].disabled = True
        elif user and user.is_client_owner():
            self.fields["store"].queryset = user.client.stores.filter(is_active=True)
