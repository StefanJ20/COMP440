from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import BaseUser


def normalize_phone(value):
    value = value.strip()
    digits = "".join(character for character in value if character.isdigit())

    if value.startswith("+") and len(digits) >= 10:
        return f"+{digits}"

    if len(digits) == 10:
        return f"+1{digits}"

    if len(digits) >= 10:
        return f"+{digits}"

    raise ValidationError(
        "Enter a valid email address or phone number."
    )


class RegistrationForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email_or_phone = forms.CharField(label="Email or phone")
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput,
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()

        if BaseUser.objects.filter(username__iexact=username).exists():
            raise ValidationError(
                "That username is already taken."
            )

        return username

    def clean_email_or_phone(self):
        value = self.cleaned_data["email_or_phone"].strip()

        try:
            validate_email(value)
        except ValidationError:
            phone = normalize_phone(value)

            if BaseUser.objects.filter(phone_number=phone).exists():
                raise ValidationError(
                    "That phone number is already registered."
                )

            self.cleaned_data["identifier_type"] = "phone"
            return phone

        email = value.lower()

        if BaseUser.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "That email address is already registered."
            )

        self.cleaned_data["identifier_type"] = "email"
        return email

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if (
            password
            and confirm_password
            and password != confirm_password
        ):
            self.add_error(
                "confirm_password",
                "Passwords do not match.",
            )

        if password:
            try:
                password_validation.validate_password(password)
            except ValidationError as error:
                self.add_error("password", error)

        return cleaned_data

    def save(self):
        identifier = self.cleaned_data["email_or_phone"]
        identifier_type = self.cleaned_data["identifier_type"]

        user = BaseUser(
            username=self.cleaned_data["username"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            email=identifier if identifier_type == "email" else "",
            phone_number=identifier if identifier_type == "phone" else None,
        )

        user.set_password(self.cleaned_data["password"])
        user.save()

        return user