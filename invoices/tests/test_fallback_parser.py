"""
FinVibe — Tests for fallback parser.
"""
from decimal import Decimal

from django.test import TestCase

from invoices.services.fallback_parser import (
    FallbackResult,
    parse_invoice_fallback,
    _extract_amount,
    _extract_date,
    _extract_vendor,
    _extract_category,
)


class AmountExtractionTest(TestCase):
    """Test amount extraction from various invoice formats."""

    def test_total_with_rupee_symbol(self) -> None:
        text = "Subtotal: ₹5,000.00\nGST: ₹900.00\nTotal: ₹5,900.00"
        amount, _ = _extract_amount(text)
        self.assertEqual(amount, Decimal("5900.00"))

    def test_total_with_rs_prefix(self) -> None:
        text = "Amount Due: Rs. 12,345.67"
        amount, _ = _extract_amount(text)
        self.assertEqual(amount, Decimal("12345.67"))

    def test_total_with_inr_prefix(self) -> None:
        text = "Total Amount: INR 8500.00"
        amount, _ = _extract_amount(text)
        self.assertEqual(amount, Decimal("8500.00"))

    def test_dollar_amount(self) -> None:
        text = "Total: $1,234.56"
        amount, _ = _extract_amount(text)
        self.assertEqual(amount, Decimal("1234.56"))

    def test_balance_due_keyword(self) -> None:
        text = "Balance Due: 25000.00"
        amount, _ = _extract_amount(text)
        self.assertEqual(amount, Decimal("25000.00"))

    def test_no_amount_found(self) -> None:
        text = "This is a random text with no numbers"
        amount, _ = _extract_amount(text)
        self.assertIsNone(amount)

    def test_grand_total_keyword(self) -> None:
        text = "Subtotal: 1000\nTax: 180\nGrand Total: ₹1,180.00"
        amount, _ = _extract_amount(text)
        self.assertEqual(amount, Decimal("1180.00"))


class DateExtractionTest(TestCase):
    """Test date extraction from various formats."""

    def test_iso_format(self) -> None:
        text = "Invoice Date: 2025-01-15"
        result = _extract_date(text)
        self.assertEqual(result, "2025-01-15")

    def test_dd_mm_yyyy_slash(self) -> None:
        text = "Date: 15/01/2025"
        result = _extract_date(text)
        self.assertEqual(result, "2025-01-15")

    def test_dd_mon_yyyy(self) -> None:
        text = "Date: 15 January 2025"
        result = _extract_date(text)
        self.assertEqual(result, "2025-01-15")

    def test_mon_dd_yyyy(self) -> None:
        text = "Date: January 15, 2025"
        result = _extract_date(text)
        self.assertEqual(result, "2025-01-15")

    def test_short_month(self) -> None:
        text = "Bill Date: 05 Feb 2025"
        result = _extract_date(text)
        self.assertEqual(result, "2025-02-05")

    def test_no_date_found(self) -> None:
        text = "No date information in this text"
        result = _extract_date(text)
        self.assertIsNone(result)


class VendorExtractionTest(TestCase):
    """Test vendor name extraction."""

    def test_vendor_keyword(self) -> None:
        text = "Vendor: Tata Consultancy Services\nDate: 2025-01-01"
        result = _extract_vendor(text)
        self.assertEqual(result, "Tata Consultancy Services")

    def test_from_keyword(self) -> None:
        text = "From: Amazon Web Services\nInvoice: AWS-123"
        result = _extract_vendor(text)
        self.assertEqual(result, "Amazon Web Services")

    def test_company_keyword(self) -> None:
        text = "Company: Infosys Limited\nBill Amount: 50000"
        result = _extract_vendor(text)
        self.assertEqual(result, "Infosys Limited")

    def test_fallback_first_line(self) -> None:
        text = "Reliance Jio Infocomm\nBill No: 12345\nAmount: 2499"
        result = _extract_vendor(text)
        self.assertEqual(result, "Reliance Jio Infocomm")


class CategoryExtractionTest(TestCase):
    """Test category classification."""

    def test_travel_keywords(self) -> None:
        text = "Flight booking from Mumbai to Delhi via IndiGo airline"
        result = _extract_category(text)
        self.assertEqual(result, "Travel")

    def test_software_keywords(self) -> None:
        text = "AWS cloud hosting subscription monthly charges"
        result = _extract_category(text)
        self.assertEqual(result, "Software & SaaS")

    def test_food_keywords(self) -> None:
        text = "Swiggy corporate meal order for team lunch"
        result = _extract_category(text)
        self.assertEqual(result, "Food & Beverage")

    def test_utilities_keywords(self) -> None:
        text = "Maharashtra electricity board power bill"
        result = _extract_category(text)
        self.assertEqual(result, "Utilities")

    def test_unknown_defaults_to_other(self) -> None:
        text = "Random invoice with no category indicators"
        result = _extract_category(text)
        self.assertEqual(result, "Other")


class FallbackParserIntegrationTest(TestCase):
    """Test the full fallback parser pipeline."""

    def test_complete_invoice(self) -> None:
        text = (
            "Vendor: Tata Consultancy Services\n"
            "Invoice Date: 15/01/2025\n"
            "Description: Software Development Services\n"
            "Total Amount: ₹2,95,000.00\n"
        )
        result = parse_invoice_fallback(text)
        self.assertIsInstance(result, FallbackResult)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.amount, Decimal("295000.00"))
        self.assertEqual(result.date, "2025-01-15")
        self.assertEqual(result.vendor_name, "Tata Consultancy Services")
        self.assertIn(result.category, ["Professional Services", "Software & SaaS", "Other"])

    def test_minimal_invoice(self) -> None:
        text = "Total: ₹500.00"
        result = parse_invoice_fallback(text)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.amount, Decimal("500.00"))

    def test_empty_text(self) -> None:
        result = parse_invoice_fallback("")
        self.assertFalse(result.is_valid)

    def test_short_text(self) -> None:
        result = parse_invoice_fallback("Hi")
        self.assertFalse(result.is_valid)

    def test_confidence_range(self) -> None:
        text = "From: Test Corp\nDate: 2025-01-01\nTotal: ₹1000\nFlight booking"
        result = parse_invoice_fallback(text)
        self.assertGreaterEqual(result.confidence, 0.20)
        self.assertLessEqual(result.confidence, 0.40)

    def test_method_is_fallback(self) -> None:
        text = "Total Amount: ₹5000.00"
        result = parse_invoice_fallback(text)
        self.assertEqual(result.method, "fallback")
