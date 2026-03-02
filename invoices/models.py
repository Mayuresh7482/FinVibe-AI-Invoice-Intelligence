"""
FinVibe — Invoice model with full AI parsing metadata and audit support.
"""
import hashlib
import uuid
from decimal import Decimal
from typing import Optional

from django.db import models
from django.utils import timezone


class CategoryChoices(models.TextChoices):
    """Controlled vocabulary for invoice categories."""
    TRAVEL = "Travel", "Travel"
    SUPPLIES = "Supplies", "Supplies"
    UTILITIES = "Utilities", "Utilities"
    PROFESSIONAL_SERVICES = "Professional Services", "Professional Services"
    FOOD_BEVERAGE = "Food & Beverage", "Food & Beverage"
    RENT = "Rent", "Rent"
    INSURANCE = "Insurance", "Insurance"
    MARKETING = "Marketing", "Marketing"
    SOFTWARE = "Software & SaaS", "Software & SaaS"
    HARDWARE = "Hardware", "Hardware"
    TELECOM = "Telecom", "Telecom"
    MAINTENANCE = "Maintenance", "Maintenance"
    OTHER = "Other", "Other"


class Invoice(models.Model):
    """
    Core invoice record — stores raw text, AI-parsed fields,
    confidence scores, and full audit metadata.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Core fields ─────────────────────────────────────────────────
    vendor_name = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Vendor / supplier name (auto-extracted or manual).",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total invoice amount (non-negative).",
    )
    date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Invoice date (parsed from raw text or entered manually).",
    )
    category = models.CharField(
        max_length=50,
        choices=CategoryChoices.choices,
        default=CategoryChoices.OTHER,
        help_text="Expense category.",
    )
    currency = models.CharField(
        max_length=3,
        default="INR",
        help_text="ISO 4217 currency code.",
    )

    # ── Raw input ───────────────────────────────────────────────────
    raw_text = models.TextField(
        help_text="Paste the raw invoice text here for AI extraction.",
    )

    # ── AI metadata ─────────────────────────────────────────────────
    parsed_by_ai = models.BooleanField(
        default=False,
        help_text="True if fields were set by AI extraction.",
    )
    ai_confidence = models.FloatField(
        null=True,
        blank=True,
        help_text="Confidence score from AI (0.0–1.0).",
    )
    ai_response = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw AI response stored for audit trail.",
    )
    parsing_error = models.TextField(
        blank=True,
        help_text="Error details if AI parsing failed.",
    )

    # ── Processing metadata ─────────────────────────────────────────
    parsed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last successful parse.",
    )
    parsed_attempts = models.PositiveIntegerField(
        default=0,
        help_text="Count of parse attempts (for idempotency).",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA-256 hash of raw_text for dedup.",
    )

    # ── Timestamps ──────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vendor_name", "date"], name="idx_vendor_date"),
            models.Index(fields=["category"], name="idx_category"),
            models.Index(fields=["parsed_by_ai"], name="idx_parsed_by_ai"),
        ]
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"

    def __str__(self) -> str:
        vendor = self.vendor_name or "Unknown"
        return f"Invoice #{self.short_id} — {vendor} — ₹{self.amount}"

    # ── Helpers ─────────────────────────────────────────────────────
    @property
    def short_id(self) -> str:
        """First 8 chars of UUID for display."""
        return str(self.id)[:8]

    @property
    def confidence_level(self) -> str:
        """Human-readable confidence label with color hint."""
        if self.ai_confidence is None:
            return "unknown"
        if self.ai_confidence >= 0.85:
            return "high"
        if self.ai_confidence >= 0.6:
            return "medium"
        return "low"

    def compute_content_hash(self) -> str:
        """SHA-256 hash of stripped raw_text for duplicate detection."""
        normalized = self.raw_text.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs) -> None:
        """Auto-compute content_hash before saving."""
        if self.raw_text:
            self.content_hash = self.compute_content_hash()
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """
    Immutable audit trail — who did what on which invoice.
    """

    class ActionChoices(models.TextChoices):
        CREATED = "CREATED", "Created"
        AI_PARSED = "AI_PARSED", "AI Parsed"
        AI_FAILED = "AI_FAILED", "AI Failed"
        FALLBACK_PARSED = "FALLBACK_PARSED", "Fallback Parsed"
        MANUAL_EDIT = "MANUAL_EDIT", "Manual Edit"
        AI_ACCEPTED = "AI_ACCEPTED", "AI Accepted"
        AI_REJECTED = "AI_REJECTED", "AI Rejected"
        REPARSE_TRIGGERED = "REPARSE_TRIGGERED", "Re-parse Triggered"
        DELETED = "DELETED", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    action = models.CharField(
        max_length=50,
        choices=ActionChoices.choices,
    )
    actor = models.CharField(
        max_length=150,
        default="system",
        help_text="Username or 'system' for automated actions.",
    )
    details = models.JSONField(
        null=True,
        blank=True,
        help_text="Snapshot of changed fields / AI response summary.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self) -> str:
        return f"[{self.action}] Invoice {self.invoice.short_id} by {self.actor}"
