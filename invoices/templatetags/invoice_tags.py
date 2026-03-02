"""
FinVibe — Custom template tags for invoice display.
"""
from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def confidence_color(value: float) -> str:
    """Return Bootstrap color class based on confidence score."""
    if value is None:
        return "secondary"
    if value >= 0.85:
        return "success"
    if value >= 0.6:
        return "warning"
    return "danger"


@register.filter
def confidence_pct(value: float) -> str:
    """Format confidence as percentage string."""
    if value is None:
        return "—"
    return f"{value * 100:.0f}%"


@register.filter
def confidence_badge(value: float) -> str:
    """Return HTML badge for confidence score."""
    if value is None:
        return format_html('<span class="badge bg-secondary">N/A</span>')
    pct = value * 100
    if value >= 0.85:
        cls = "bg-success"
    elif value >= 0.6:
        cls = "bg-warning text-dark"
    else:
        cls = "bg-danger"
    pct_str = f"{pct:.0f}%"
    return format_html(
        '<span class="badge {}">{}</span>', cls, pct_str,
    )


@register.filter
def currency_format(value, currency="INR") -> str:
    """Format amount with currency symbol."""
    symbols = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}
    symbol = symbols.get(str(currency).upper(), currency)
    try:
        return f"{symbol}{float(value):,.2f}"
    except (TypeError, ValueError):
        return f"{symbol}0.00"


@register.filter
def truncate_middle(value: str, length: int = 50) -> str:
    """Truncate string in the middle for display."""
    if not value or len(value) <= length:
        return value or ""
    half = (length - 3) // 2
    return f"{value[:half]}...{value[-half:]}"
