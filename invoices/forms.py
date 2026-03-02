"""
FinVibe — Invoice forms with AI parse integration.
"""
from django import forms
from invoices.models import Invoice, CategoryChoices


class InvoiceForm(forms.ModelForm):
    """Form for creating/editing invoices with AI parsing support."""

    force_reparse = forms.BooleanField(
        required=False,
        initial=False,
        label="Force Re-parse",
        help_text="Check to re-run AI extraction even if already parsed.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Invoice
        fields = [
            "raw_text", "vendor_name", "amount", "date",
            "category", "currency",
        ]
        widgets = {
            "raw_text": forms.Textarea(attrs={
                "class": "form-control font-monospace",
                "rows": 10,
                "placeholder": "Paste raw invoice text here...",
                "id": "id_raw_text",
            }),
            "vendor_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Auto-filled by AI",
                "id": "id_vendor_name",
            }),
            "amount": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "placeholder": "Auto-filled by AI",
                "id": "id_amount",
            }),
            "date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
                "id": "id_date",
            }),
            "category": forms.Select(attrs={
                "class": "form-select",
                "id": "id_category",
            }),
            "currency": forms.TextInput(attrs={
                "class": "form-control",
                "maxlength": 3,
                "id": "id_currency",
            }),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount < 0:
            raise forms.ValidationError("Amount cannot be negative.")
        return amount


class InvoiceSearchForm(forms.Form):
    """Search and filter form for the dashboard."""

    q = forms.CharField(
        required=False,
        label="Search vendor",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Search vendor name...",
            "id": "id_search",
            "autocomplete": "off",
        }),
    )
    category = forms.ChoiceField(
        required=False,
        choices=[("", "All Categories")] + CategoryChoices.choices,
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_filter_category",
        }),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "type": "date",
            "id": "id_date_from",
        }),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "type": "date",
            "id": "id_date_to",
        }),
    )
    parsed = forms.ChoiceField(
        required=False,
        choices=[("", "All"), ("ai", "AI Parsed"), ("manual", "Manual / Fallback")],
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_filter_parsed",
        }),
    )
