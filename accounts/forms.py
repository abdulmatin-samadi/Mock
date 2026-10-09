from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User


class RegisterForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={"placeholder": "Ali", "autocomplete": "given-name", "autofocus": True}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(
        attrs={"placeholder": "Valiyev", "autocomplete": "family-name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "you@example.com", "autocomplete": "email"}))
    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(
        attrs={"placeholder": "At least 8 characters", "autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput(
        attrs={"placeholder": "Repeat your password", "autocomplete": "new-password"}))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1:
            temp = User(email=data.get("email", ""), first_name=data.get("first_name", ""),
                        last_name=data.get("last_name", ""))
            try:
                password_validation.validate_password(p1, temp)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return data


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(
        attrs={"autofocus": True, "autocomplete": "email", "placeholder": "you@example.com"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].widget.attrs["placeholder"] = "Your password"


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "profile_photo", "phone_number"]
        widgets = {
            "profile_photo": forms.FileInput(attrs={"accept": "image/*"}),
            "phone_number": forms.TextInput(attrs={"placeholder": "+998 90 123 45 67", "autocomplete": "tel"}),
        }
