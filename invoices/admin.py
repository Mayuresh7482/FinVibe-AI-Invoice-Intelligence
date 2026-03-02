"""
FinVibe — Custom admin for Invoice with AI parse integration.
"""
from django.contrib import admin
from django.utils.html import format_html

from invoices.models import AuditLog, Invoice
from invoices.services.invoice_processor import process_invoice


class AuditLogInline(admin.TabularInline):
    """Inline audit log display in Invoice admin."""
    model = AuditLog
    extra = 0
    readonly_fields = ("action", "actor", "details", "created_at")
    can_delete = False
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """
    Invoice admin with:
    - AI parse on save
    - Confidence color badges
    - Inline audit logs
    - Search and filters
    """
    list_display = (
        "short_id", "vendor_name", "amount_display", "date",
        "category", "confidence_badge", "parsed_by_ai", "created_at",
    )
    list_filter = ("category", "parsed_by_ai", "date")
    search_fields = ("vendor_name", "raw_text")
    readonly_fields = (
        "id", "parsed_by_ai", "ai_confidence", "ai_response",
        "parsing_error", "parsed_at", "parsed_attempts",
        "content_hash", "created_at", "updated_at",
    )
    inlines = [AuditLogInline]
    ordering = ("-created_at",)
    list_per_page = 25

    fieldsets = (
        ("📝 Raw Input", {
            "fields": ("raw_text",),
            "description": "Paste the raw invoice text below. AI will extract fields on save.",
        }),
        ("📊 Extracted Fields", {
            "fields": ("vendor_name", "amount", "date", "category", "currency"),
        }),
        ("🤖 AI Metadata", {
            "classes": ("collapse",),
            "fields": (
                "parsed_by_ai", "ai_confidence", "ai_response",
                "parsing_error", "parsed_at", "parsed_attempts",
            ),
        }),
        ("🔧 System", {
            "classes": ("collapse",),
            "fields": ("id", "content_hash", "created_at", "updated_at"),
        }),
    )

    def amount_display(self, obj: Invoice) -> str:
        return f"₹{obj.amount:,.2f}"
    amount_display.short_description = "Amount"
    amount_display.admin_order_field = "amount"

    def confidence_badge(self, obj: Invoice) -> str:
        if obj.ai_confidence is None:
            return format_html('<span style="color:#999;">—</span>')
        pct = obj.ai_confidence * 100
        if obj.ai_confidence >= 0.85:
            color = "#198754"  # green
        elif obj.ai_confidence >= 0.6:
            color = "#ffc107"  # yellow
        else:
            color = "#dc3545"  # red
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; '
            'border-radius:10px; font-size:12px; font-weight:600;">'
            '{:.0f}%</span>',
            color, pct,
        )
    confidence_badge.short_description = "Confidence"
    confidence_badge.admin_order_field = "ai_confidence"

    def save_model(self, request, obj, form, change):
        """Trigger AI parsing on save if raw_text present."""
        is_new = not change
        force = request.POST.get("force_reparse", False)
        actor = request.user.username or "admin"

        # Save first to get an ID
        super().save_model(request, obj, form, change)

        # Trigger AI parse if new or forced
        if is_new or force or (not obj.parsed_by_ai and obj.raw_text):
            success, message = process_invoice(
                invoice=obj,
                actor=actor,
                force_reparse=bool(force),
                overwrite_fields=bool(force),
            )
            if not success:
                self.message_user(request, f"⚠️ Parsing issue: {message}", level="warning")
            else:
                self.message_user(request, f"✅ {message}")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("invoice", "action", "actor", "created_at")
    list_filter = ("action",)
    readonly_fields = ("invoice", "action", "actor", "details", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
