from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from clients.models import Client
from .models import User


class VendoraLoginForm(AuthenticationForm):
    username = forms.CharField(label="Email or username", widget=forms.TextInput(attrs={"autofocus": True}))

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and "@" in username:
            matched_user = User.objects.filter(email__iexact=username).first()
            if matched_user:
                self.cleaned_data["username"] = matched_user.get_username()
        return super().clean()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_super_admin():
            return
        if not user.client_id or user.client.status != "active":
            raise forms.ValidationError("This business account is not active. Contact VendoraOps support.", code="inactive_client")
        if user.is_manager() and (not user.store_id or not user.store.is_active):
            raise forms.ValidationError("Your assigned store is inactive or missing. Contact your business owner.", code="inactive_store")


MANAGER_PERMISSION_FIELDS = (
    "can_manage_inventory",
    "can_manage_paidouts",
    "can_close_day",
    "can_view_reports",
    "can_manage_pos",
)


class ManagerCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "store", *MANAGER_PERMISSION_FIELDS, "password1", "password2")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_user = user
        if user and user.is_client_owner():
            self.fields["store"].queryset = user.client.stores.filter(is_active=True)
        self._label_permission_fields()

    def _label_permission_fields(self):
        labels = {
            "can_manage_inventory": "Inventory and purchases",
            "can_manage_paidouts": "Paid-outs",
            "can_close_day": "Daily close",
            "can_view_reports": "Reports and profit/loss",
            "can_manage_pos": "POS sales and sync",
        }
        for field, label in labels.items():
            self.fields[field].label = label

    def clean_store(self):
        store = self.cleaned_data.get("store")
        if self.request_user and self.request_user.is_client_owner() and not store:
            raise forms.ValidationError("Manager must be assigned to one active store.")
        return store

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.MANAGER
        if user.store_id:
            user.client = user.store.client
        if commit:
            user.save()
        return user


class ManagerEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "store", "is_active", *MANAGER_PERMISSION_FIELDS)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_user = user
        if user and user.is_client_owner():
            self.fields["store"].queryset = user.client.stores.filter(is_active=True)
        ManagerCreationForm._label_permission_fields(self)

    def clean_store(self):
        store = self.cleaned_data.get("store")
        if self.request_user and self.request_user.is_client_owner() and not store:
            raise forms.ValidationError("Manager must be assigned to one active store.")
        return store


class ClientOwnerCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "client", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.CLIENT_OWNER
        if commit:
            user.save()
        return user


class ClientMessageForm(forms.Form):
    recipient = forms.ChoiceField(choices=())
    client = forms.ModelChoiceField(queryset=Client.objects.none(), required=False)
    subject = forms.CharField(max_length=160)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user and user.is_super_admin():
            self.fields["recipient"].choices = (("all", "All clients"), ("client", "Selected client"))
            self.fields["client"].queryset = Client.objects.filter(status=Client.ACTIVE)
        else:
            self.fields["recipient"].choices = (("platform", "VendoraOps support"),)
            self.fields["recipient"].widget = forms.HiddenInput()
            self.fields["client"].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        if self.user and self.user.is_super_admin() and cleaned.get("recipient") == "client" and not cleaned.get("client"):
            self.add_error("client", "Choose the client for this message.")
        return cleaned
