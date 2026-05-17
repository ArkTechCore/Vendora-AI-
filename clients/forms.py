from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from .models import Client


class ClientEditForm(forms.ModelForm):
    owner_username = forms.CharField(max_length=150)
    owner_email = forms.EmailField()
    owner_first_name = forms.CharField(max_length=150, required=False)
    owner_last_name = forms.CharField(max_length=150, required=False)
    password1 = forms.CharField(label="New owner password", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Confirm new owner password", widget=forms.PasswordInput, required=False)

    class Meta:
        model = Client
        fields = ("name", "owner_name", "email", "phone", "street_address", "city", "state", "postal_code", "country", "status")

    def clean(self):
        cleaned = super().clean()
        self._sync_legacy_address(cleaned)
        return cleaned

    def _sync_legacy_address(self, cleaned):
        parts = [
            cleaned.get("street_address", ""),
            cleaned.get("city", ""),
            cleaned.get("state", ""),
            cleaned.get("postal_code", ""),
            cleaned.get("country", ""),
        ]
        cleaned["address"] = ", ".join(part for part in parts if part)

    def save(self, commit=True):
        client = super().save(commit=False)
        client.address = self.cleaned_data.get("address", "")
        if commit:
            client.save()
            self.save_m2m()
        return client

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner_user = None
        if self.instance and self.instance.pk:
            self.owner_user = self.instance.users.filter(role=User.CLIENT_OWNER).first()
        if self.owner_user:
            self.fields["owner_username"].initial = self.owner_user.username
            self.fields["owner_email"].initial = self.owner_user.email
            self.fields["owner_first_name"].initial = self.owner_user.first_name
            self.fields["owner_last_name"].initial = self.owner_user.last_name

    def clean_owner_username(self):
        username = self.cleaned_data["owner_username"]
        qs = User.objects.filter(username__iexact=username)
        if self.owner_user:
            qs = qs.exclude(pk=self.owner_user.pk)
        if qs.exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean_owner_email(self):
        email = self.cleaned_data["owner_email"]
        qs = User.objects.filter(email__iexact=email)
        if self.owner_user:
            qs = qs.exclude(pk=self.owner_user.pk)
        if qs.exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 or password2:
            if password1 != password2:
                raise forms.ValidationError("Owner passwords do not match.")
            try:
                validate_password(password1, self.owner_user)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        client = super().save(commit=commit)
        owner = self.owner_user
        if owner is None:
            owner = User(role=User.CLIENT_OWNER, client=client)
        owner.username = self.cleaned_data["owner_username"]
        owner.email = self.cleaned_data["owner_email"]
        owner.first_name = self.cleaned_data.get("owner_first_name", "")
        owner.last_name = self.cleaned_data.get("owner_last_name", "")
        owner.role = User.CLIENT_OWNER
        owner.client = client
        owner.store = None
        if self.cleaned_data.get("password1"):
            owner.set_password(self.cleaned_data["password1"])
        elif owner.pk is None:
            owner.set_unusable_password()
        owner.save()
        return client


class ClientOnboardingForm(forms.Form):
    name = forms.CharField(label="Business name", max_length=160)
    owner_name = forms.CharField(max_length=160)
    email = forms.EmailField(label="Business email")
    phone = forms.CharField(max_length=40, required=False)
    street_address = forms.CharField(max_length=255, required=False, label="Street address")
    city = forms.CharField(max_length=120, required=False)
    state = forms.CharField(max_length=80, required=False)
    postal_code = forms.CharField(max_length=20, required=False, label="ZIP / postal code")
    country = forms.CharField(max_length=2, initial="US")
    status = forms.ChoiceField(choices=Client.STATUS_CHOICES, initial=Client.ACTIVE)
    owner_username = forms.CharField(max_length=150)
    owner_email = forms.EmailField()
    owner_first_name = forms.CharField(max_length=150, required=False)
    owner_last_name = forms.CharField(max_length=150, required=False)
    password1 = forms.CharField(label="Owner password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm owner password", widget=forms.PasswordInput)

    def clean_owner_username(self):
        username = self.cleaned_data["owner_username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean_owner_email(self):
        email = self.cleaned_data["owner_email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            raise forms.ValidationError("Owner passwords do not match.")
        password = cleaned.get("password1")
        if password:
            try:
                validate_password(password)
            except ValidationError as exc:
                self.add_error("password1", exc)
        parts = [
            cleaned.get("street_address", ""),
            cleaned.get("city", ""),
            cleaned.get("state", ""),
            cleaned.get("postal_code", ""),
            cleaned.get("country", ""),
        ]
        cleaned["address"] = ", ".join(part for part in parts if part)
        return cleaned

    @transaction.atomic
    def save(self):
        client = Client.objects.create(
            name=self.cleaned_data["name"],
            owner_name=self.cleaned_data["owner_name"],
            email=self.cleaned_data["email"],
            phone=self.cleaned_data.get("phone", ""),
            address=self.cleaned_data.get("address", ""),
            street_address=self.cleaned_data.get("street_address", ""),
            city=self.cleaned_data.get("city", ""),
            state=self.cleaned_data.get("state", ""),
            postal_code=self.cleaned_data.get("postal_code", ""),
            country=self.cleaned_data.get("country", "US"),
            status=self.cleaned_data["status"],
        )
        owner = User.objects.create_user(
            username=self.cleaned_data["owner_username"],
            email=self.cleaned_data["owner_email"],
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data.get("owner_first_name", ""),
            last_name=self.cleaned_data.get("owner_last_name", ""),
            role=User.CLIENT_OWNER,
            client=client,
        )
        return client, owner
