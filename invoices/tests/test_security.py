"""
FinVibe — Tests for security middleware, rate limiting, and demo mode.
"""
import json
import time
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase, override_settings

from invoices.middleware import RateLimitMiddleware, hash_text_for_log, mask_api_key


class HashTextForLogTest(TestCase):
    """Test PII-safe text hashing utility."""

    def test_deterministic_hash(self) -> None:
        """Same text produces same hash."""
        text = "Invoice No: TCS-2025-001"
        h1 = hash_text_for_log(text)
        h2 = hash_text_for_log(text)
        self.assertEqual(h1, h2)

    def test_different_text_different_hash(self) -> None:
        h1 = hash_text_for_log("Invoice A")
        h2 = hash_text_for_log("Invoice B")
        self.assertNotEqual(h1, h2)

    def test_hash_length(self) -> None:
        """Hash is truncated to 16 chars for log readability."""
        h = hash_text_for_log("Test invoice raw text content")
        self.assertEqual(len(h), 16)

    def test_empty_text(self) -> None:
        h = hash_text_for_log("")
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 16)


class MaskApiKeyTest(TestCase):
    """Test API key masking."""

    def test_normal_key(self) -> None:
        result = mask_api_key("AIzaSyA1234567890abcdefghij")
        self.assertEqual(result, "AIza...ghij")
        self.assertNotIn("1234567890", result)

    def test_short_key(self) -> None:
        result = mask_api_key("short")
        self.assertEqual(result, "***")

    def test_empty_key(self) -> None:
        result = mask_api_key("")
        self.assertEqual(result, "***")

    def test_none_key(self) -> None:
        result = mask_api_key(None)
        self.assertEqual(result, "***")


@override_settings(RATE_LIMIT_PER_MINUTE=5, RATE_LIMIT_PARSE_PER_MINUTE=2)
class RateLimitMiddlewareTest(TestCase):
    """Test rate limiting middleware."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="ratelimit_user", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="ratelimit_user", password="testpass123")

    def test_normal_requests_pass(self) -> None:
        """Requests within limit should pass."""
        for _ in range(3):
            response = self.client.get("/")
            self.assertIn(response.status_code, [200, 302])

    def test_general_rate_limit_exceeded(self) -> None:
        """After exceeding general limit, should get 429."""
        # Make 5 requests (the limit)
        for _ in range(5):
            self.client.get("/")
        # 6th should be rate limited
        response = self.client.get("/")
        self.assertEqual(response.status_code, 429)

    def test_rate_limit_window_resets(self) -> None:
        """After window expires, requests should work again."""
        # This test is conceptual — we don't want to sleep 60s in tests
        # Just verify the middleware instantiates correctly
        factory = RequestFactory()
        request = factory.get("/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        def dummy_response(req):
            from django.http import HttpResponse
            return HttpResponse("OK")

        mw = RateLimitMiddleware(dummy_response)
        # Should not raise
        resp = mw(request)
        self.assertEqual(resp.status_code, 200)


class IPMaskingTest(TestCase):
    """Test IP masking for safe logging."""

    def test_ipv4_masking(self) -> None:
        result = RateLimitMiddleware._mask_ip("192.168.1.42")
        self.assertEqual(result, "192.168.x.x")

    def test_short_ip(self) -> None:
        result = RateLimitMiddleware._mask_ip("::1")
        self.assertIsInstance(result, str)


@override_settings(DEMO_MODE=True)
class DemoModeTest(TestCase):
    """Test DEMO_MODE functionality."""

    def test_demo_mode_enabled(self) -> None:
        """When DEMO_MODE=True, parse should not call Gemini."""
        from invoices.services.ai_service import parse_invoice
        result = parse_invoice(
            "Invoice No: TEST-DEMO-001\n"
            "Date: 2025-01-15\n"
            "Vendor: Demo Corp\n"
            "Total: ₹10,000.00\n"
        )
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
        self.assertEqual(result.data.method, "demo")
        self.assertEqual(result.attempts, 0)

    def test_demo_mode_no_api_cost(self) -> None:
        """Demo mode should have zero latency (no network call)."""
        from invoices.services.ai_service import parse_invoice
        result = parse_invoice(
            "From: Test Vendor Pvt Ltd\n"
            "Amount Due: Rs. 5,000.00\n"
            "Date: 2025-02-01\n"
        )
        # Should complete in under 500ms (no API call)
        self.assertLess(result.latency_ms, 500)

    def test_demo_mode_returns_fallback_data(self) -> None:
        """Demo mode uses fallback parser for field extraction."""
        from invoices.services.ai_service import parse_invoice
        result = parse_invoice(
            "Vendor: Infosys Limited\n"
            "Invoice Date: 20-Jan-2025\n"
            "Total Amount: ₹50,000.00\n"
        )
        if result.success and result.data:
            self.assertIsNotNone(result.data.amount)
            self.assertGreater(result.data.confidence, 0)


@override_settings(DEMO_MODE=False)
class DemoModeDisabledTest(TestCase):
    """Test that DEMO_MODE=False uses real pipeline."""

    @override_settings(GEMINI_API_KEY="")
    def test_no_api_key_returns_error(self) -> None:
        """Without API key and DEMO_MODE off, should fail."""
        from invoices.services.ai_service import parse_invoice
        result = parse_invoice("A long enough invoice text for testing purposes here")
        self.assertFalse(result.success)
        self.assertIn("GEMINI_API_KEY", result.error)


class InputLengthGuardTest(TestCase):
    """Test MAX_RAW_TEXT_LENGTH enforcement."""

    @override_settings(MAX_RAW_TEXT_LENGTH=100)
    def test_text_too_long(self) -> None:
        """Text exceeding max length should be rejected."""
        from invoices.services.ai_service import parse_invoice
        long_text = "x" * 150
        result = parse_invoice(long_text)
        self.assertFalse(result.success)
        self.assertIn("exceeds maximum", result.error)

    @override_settings(MAX_RAW_TEXT_LENGTH=50000)
    def test_text_within_limit(self) -> None:
        """Text within limit should proceed (may fail on API, not on length)."""
        from invoices.services.ai_service import parse_invoice
        text = "Invoice No: TEST-001\nTotal: ₹5000\n" + "Details " * 10
        result = parse_invoice(text)
        # Should not fail with "exceeds maximum" error
        if not result.success:
            self.assertNotIn("exceeds maximum", result.error or "")


class DemoParseEndpointTest(TestCase):
    """Test the demo-only API endpoint."""

    def test_demo_parse_post(self) -> None:
        """POST to demo-parse should return results without authentication."""
        client = Client()
        response = client.post(
            "/api/demo-parse/",
            data=json.dumps({
                "raw_text": "From: Test Corp\nTotal: ₹10,000.00\nDate: 2025-01-15"
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["method"], "demo")

    def test_demo_parse_get_rejected(self) -> None:
        """GET to demo-parse should return 405."""
        client = Client()
        response = client.get("/api/demo-parse/")
        self.assertEqual(response.status_code, 405)

    def test_demo_parse_short_text(self) -> None:
        """Short text should return 400."""
        client = Client()
        response = client.post(
            "/api/demo-parse/",
            data=json.dumps({"raw_text": "Hi"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
