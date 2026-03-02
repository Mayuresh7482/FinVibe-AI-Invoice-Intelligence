"""
FinVibe — Tests for AI service (mocked Gemini).
"""
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from invoices.services.ai_service import (
    AIServiceResult,
    ParsedInvoice,
    _extract_json_from_response,
    _normalize_amount,
    _normalize_category,
    _validate_response,
    parse_invoice,
)


class NormalizeAmountTest(TestCase):
    """Test amount normalization."""

    def test_float_input(self) -> None:
        self.assertEqual(_normalize_amount(1234.56), Decimal("1234.56"))

    def test_int_input(self) -> None:
        self.assertEqual(_normalize_amount(5000), Decimal("5000.00"))

    def test_string_with_commas(self) -> None:
        self.assertEqual(_normalize_amount("12,345.67"), Decimal("12345.67"))

    def test_string_with_rupee_symbol(self) -> None:
        self.assertEqual(_normalize_amount("₹10,000.00"), Decimal("10000.00"))

    def test_string_with_dollar(self) -> None:
        self.assertEqual(_normalize_amount("$850.00"), Decimal("850.00"))

    def test_none_input(self) -> None:
        self.assertIsNone(_normalize_amount(None))

    def test_invalid_string(self) -> None:
        self.assertIsNone(_normalize_amount("not-a-number"))

    def test_negative_returns_none(self) -> None:
        self.assertIsNone(_normalize_amount(-100))


class NormalizeCategoryTest(TestCase):
    """Test category normalization."""

    def test_exact_match(self) -> None:
        self.assertIn(
            _normalize_category("Travel"),
            ["Travel", "travel"],
        )

    def test_alias_match(self) -> None:
        self.assertEqual(_normalize_category("consulting"), "Professional Services")

    def test_keyword_in_string(self) -> None:
        self.assertEqual(_normalize_category("airline tickets"), "Travel")

    def test_unknown_returns_other(self) -> None:
        self.assertEqual(_normalize_category("quantum physics"), "Other")

    def test_none_returns_other(self) -> None:
        self.assertEqual(_normalize_category(None), "Other")

    def test_empty_returns_other(self) -> None:
        self.assertEqual(_normalize_category(""), "Other")


class ExtractJsonTest(TestCase):
    """Test JSON extraction from various response formats."""

    def test_clean_json(self) -> None:
        text = '{"amount": 1000, "confidence": 0.9}'
        result = _extract_json_from_response(text)
        self.assertEqual(result["amount"], 1000)

    def test_markdown_code_block(self) -> None:
        text = '```json\n{"amount": 500, "confidence": 0.8}\n```'
        result = _extract_json_from_response(text)
        self.assertEqual(result["amount"], 500)

    def test_json_with_surrounding_text(self) -> None:
        text = 'Here is the extracted data:\n{"amount": 2000, "confidence": 0.95}\nDone.'
        result = _extract_json_from_response(text)
        self.assertEqual(result["amount"], 2000)

    def test_invalid_json(self) -> None:
        text = "This is not JSON at all"
        result = _extract_json_from_response(text)
        self.assertIsNone(result)


class ValidateResponseTest(TestCase):
    """Test AI response validation and normalization."""

    def test_valid_response(self) -> None:
        data = {
            "amount": 10000.00,
            "currency": "INR",
            "date": "2025-01-15",
            "vendor_name": "Test Corp",
            "category": "Supplies",
            "confidence": 0.92,
        }
        result = _validate_response(data)
        self.assertIsInstance(result, ParsedInvoice)
        self.assertEqual(result.amount, Decimal("10000.00"))
        self.assertEqual(result.vendor_name, "Test Corp")
        self.assertEqual(result.confidence, 0.92)

    def test_invalid_date_format(self) -> None:
        data = {
            "amount": 500,
            "date": "15th January",
            "confidence": 0.8,
        }
        result = _validate_response(data)
        self.assertIsNone(result.date)

    def test_missing_optional_fields(self) -> None:
        data = {
            "amount": 1000,
            "confidence": 0.7,
        }
        result = _validate_response(data)
        self.assertEqual(result.amount, Decimal("1000.00"))
        self.assertIsNone(result.vendor_name)
        self.assertIsNone(result.date)

    def test_confidence_clamped(self) -> None:
        data = {"amount": 100, "confidence": 1.5}
        result = _validate_response(data)
        self.assertEqual(result.confidence, 1.0)

    def test_invalid_currency_defaults_to_inr(self) -> None:
        data = {"amount": 100, "confidence": 0.9, "currency": "INVALID"}
        result = _validate_response(data)
        self.assertEqual(result.currency, "INR")


@override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="test-model", AI_MAX_RETRIES=1)
class ParseInvoiceServiceTest(TestCase):
    """Test the main parse_invoice function with mocked Gemini."""

    def test_empty_text_returns_error(self) -> None:
        result = parse_invoice("")
        self.assertFalse(result.success)
        self.assertIn("too short", result.error)

    def test_short_text_returns_error(self) -> None:
        result = parse_invoice("Hi")
        self.assertFalse(result.success)

    @override_settings(GEMINI_API_KEY="")
    def test_missing_api_key(self) -> None:
        result = parse_invoice("A real invoice text with enough content to parse")
        self.assertFalse(result.success)
        self.assertIn("GEMINI_API_KEY", result.error)

    @patch("invoices.services.ai_service.genai")
    def test_successful_parse(self, mock_genai: MagicMock) -> None:
        """Test successful AI parse with mocked Gemini response."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "amount": 5000.00,
            "currency": "INR",
            "date": "2025-01-15",
            "vendor_name": "Test Vendor",
            "category": "Supplies",
            "confidence": 0.91,
        })
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        result = parse_invoice("A sufficiently long invoice text for testing the parser")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
        self.assertEqual(result.data.amount, Decimal("5000.00"))
        self.assertEqual(result.data.vendor_name, "Test Vendor")

    @patch("invoices.services.ai_service.genai")
    def test_empty_response(self, mock_genai: MagicMock) -> None:
        """Test handling of empty Gemini response."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        result = parse_invoice("A sufficiently long invoice text for testing empty response")
        self.assertFalse(result.success)
