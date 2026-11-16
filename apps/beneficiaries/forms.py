import secrets
from django import forms
from .models import Beneficiary, normalize_phone
from apps.programs.models import Program


class BeneficiaryForm(forms.ModelForm):
    raw_id_reference = forms.CharField(max_length=20, required=False, label="National ID Reference")
    device_id = forms.CharField(max_length=255, required=False, widget=forms.HiddenInput())

    class Meta:
        model = Beneficiary
        fields = ("program", "full_name", "phone", "village")

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        return normalize_phone(phone)

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw_id = self.cleaned_data.get("raw_id_reference")
        if raw_id:
            instance.set_id_reference(raw_id)
        
        # Generate a unique public ID if it doesn't exist
        if not instance.public_id:
            # Format: GG-YEAR-RANDOM (e.g., GG-26-A7B9)
            import datetime
            year = datetime.datetime.now().strftime("%y")
            random_part = secrets.token_hex(2).upper()
            instance.public_id = f"GG-{year}-{random_part}"
            
            # Ensure uniqueness (loop if collision, though extremely rare)
            while Beneficiary.objects.filter(public_id=instance.public_id).exists():
                random_part = secrets.token_hex(2).upper()
                instance.public_id = f"GG-{year}-{random_part}"

        if commit:
            instance.save()
        return instance
