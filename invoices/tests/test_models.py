"""
FinVibe — Tests for Invoice model.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from invoices.models import AuditLog, Invoice, CategoryChoices


class InvoiceModelTest(TestCase):
    """Test Invoice model fields, methods, and constraints."""

    def setUp(self) -> None:
        self.invoice = Invoice.objects.create(
            vendor_name="Test Vendor Pvt Ltd",
            raw_text="Invoice No: TEST-001\nDate: 2025-01-15\nTotal: ₹10,000.00",
            amount=Decimal("10000.00"),
            category=CategoryChoices.SUPPLIES,
            date=date(2025, 1, 15),
        )

    def test_invoice_creation(self) -> None:
        """Test that invoice is created with correct fields."""
        self.assertEqual(self.invoice.vendor_name, "Test Vendor Pvt Ltd")
        self.assertEqual(self.invoice.amount, Decimal("10000.00"))
        self.assertEqual(self.invoice.category, "Supplies")
        self.assertIsNotNone(self.invoice.id)
        self.assertIsNotNone(self.invoice.created_at)

    def test_str_representation(self) -> None:
        """Test __str__ includes short_id, vendor, and amount."""
        s = str(self.invoice)
        self.assertIn("Test Vendor Pvt Ltd", s)
        self.assertIn("10000.00", s)

    def test_short_id(self) -> None:
        """Test short_id returns first 8 chars of UUID."""
        self.assertEqual(len(self.invoice.short_id), 8)
        self.assertEqual(self.invoice.short_id, str(self.invoice.id)[:8])

    def test_content_hash_computed_on_save(self) -> None:
        """Test content_hash is auto-computed from raw_text."""
        self.assertNotEqual(self.invoice.content_hash, "")
        self.assertEqual(len(self.invoice.content_hash), 64)

    def test_content_hash_consistency(self) -> None:
        """Test same raw_text produces same hash."""
        hash1 = self.invoice.content_hash
        self.invoice.save()
        self.assertEqual(self.invoice.content_hash, hash1)

    def test_content_hash_differs_for_different_text(self) -> None:
        """Test different raw_text produces different hash."""
        hash1 = self.invoice.content_hash
        self.invoice.raw_text = "Completely different invoice text"
        self.invoice.save()
        self.assertNotEqual(self.invoice.content_hash, hash1)

    def test_confidence_level_high(self) -> None:
        self.invoice.ai_confidence = 0.92
        self.assertEqual(self.invoice.confidence_level, "high")

    def test_confidence_level_medium(self) -> None:
        self.invoice.ai_confidence = 0.72
        self.assertEqual(self.invoice.confidence_level, "medium")

    def test_confidence_level_low(self) -> None:
        self.invoice.ai_confidence = 0.45
        self.assertEqual(self.invoice.confidence_level, "low")

    def test_confidence_level_unknown(self) -> None:
        self.invoice.ai_confidence = None
        self.assertEqual(self.invoice.confidence_level, "unknown")

    def test_default_values(self) -> None:
        """Test defaults for new invoice."""
        inv = Invoice.objects.create(raw_text="Minimal test invoice text here")
        self.assertEqual(inv.amount, Decimal("0.00"))
        self.assertEqual(inv.category, "Other")
        self.assertEqual(inv.currency, "INR")
        self.assertFalse(inv.parsed_by_ai)
        self.assertIsNone(inv.ai_confidence)
        self.assertEqual(inv.parsed_attempts, 0)

    def test_ordering(self) -> None:
        """Test default ordering is by -created_at."""
        Invoice.objects.create(raw_text="Second invoice raw text content")
        invoices = Invoice.objects.all()
        self.assertGreaterEqual(invoices[0].created_at, invoices[1].created_at)


class AuditLogModelTest(TestCase):
    """Test AuditLog model."""

    def setUp(self) -> None:
        self.invoice = Invoice.objects.create(
            vendor_name="Audit Test Vendor",
            raw_text="Test invoice for audit logging purposes",
        )

    def test_audit_log_creation(self) -> None:
        log = AuditLog.objects.create(
            invoice=self.invoice,
            action=AuditLog.ActionChoices.CREATED,
            actor="admin",
            details={"method": "test"},
        )
        self.assertEqual(log.action, "CREATED")
        self.assertEqual(log.actor, "admin")
        self.assertIsNotNone(log.created_at)

    def test_audit_log_str(self) -> None:
        log = AuditLog.objects.create(
            invoice=self.invoice,
            action=AuditLog.ActionChoices.AI_PARSED,
            actor="system",
        )
        s = str(log)
        self.assertIn("AI_PARSED", s)
        self.assertIn("system", s)

    def test_audit_log_cascade_delete(self) -> None:
        AuditLog.objects.create(
            invoice=self.invoice,
            action=AuditLog.ActionChoices.CREATED,
            actor="admin",
        )
        self.assertEqual(AuditLog.objects.count(), 1)
        self.invoice.delete()
        self.assertEqual(AuditLog.objects.count(), 0)
