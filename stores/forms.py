from django import forms

from .models import Store


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ("client", "name", "code", "address", "phone", "is_active")
        widgets = {"address": forms.Textarea(attrs={"rows": 3, "placeholder": "Full store address for weather and local planning alerts"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["address"].required = True
