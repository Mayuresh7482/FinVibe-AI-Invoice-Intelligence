"""
FinVibe — Gemini AI service for invoice extraction.
Handles: prompt construction, API calls, retries with backoff,
rate limiting, response validation, and structured logging.
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from django.conf import settings

logger = logging.getLogger("ai_service")

# ─── Rate limiter (simple token-bucket) ────────────────────────────
_last_request_time: float = 0.0
_MIN_INTERVAL: float = 1.0  # Minimum 1 second between requests


# ─── Data classes ──────────────────────────────────────────────────
@dataclass
class ParsedInvoice:
    """Structured result from AI extraction."""
    amount: Optional[Decimal] = None
    currency: str = "INR"
    date: Optional[str] = None
    vendor_name: Optional[str] = None
    category: str = "Other"
    confidence: float = 0.0
    raw_response: Optional[Dict[str, Any]] = None
    method: str = "gemini"

    @property
    def is_valid(self) -> bool:
        return self.confidence > 0.0 and self.amount is not None


@dataclass
class AIServiceResult:
    """Wrapper for service outcome — success or failure."""
    success: bool
    data: Optional[ParsedInvoice] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    attempts: int = 0


# ─── Category mapping ─────────────────────────────────────────────
VALID_CATEGORIES = {
    "travel", "supplies", "utilities", "professional services",
    "food & beverage", "rent", "insurance", "marketing",
    "software & saas", "hardware", "telecom", "maintenance", "other",
}

CATEGORY_ALIASES: Dict[str, str] = {
    "food": "Food & Beverage",
    "food and beverage": "Food & Beverage",
    "saas": "Software & SaaS",
    "software": "Software & SaaS",
    "consulting": "Professional Services",
    "professional": "Professional Services",
    "telecom": "Telecom",
    "telecommunications": "Telecom",
    "office supplies": "Supplies",
    "office": "Supplies",
    "transport": "Travel",
    "transportation": "Travel",
    "flight": "Travel",
    "airline": "Travel",
    "hotel": "Travel",
    "cab": "Travel",
    "uber": "Travel",
    "electricity": "Utilities",
    "water": "Utilities",
    "gas": "Utilities",
    "internet": "Telecom",
    "advertising": "Marketing",
    "ads": "Marketing",
    "repair": "Maintenance",
    "cleaning": "Maintenance",
}


def _normalize_category(raw_category: Optional[str]) -> str:
    """Map AI-returned category to controlled vocabulary."""
    if not raw_category:
        return "Other"
    lowered = raw_category.strip().lower()
    if lowered in VALID_CATEGORIES:
        # Capitalize properly
        for valid in VALID_CATEGORIES:
            if valid == lowered:
                return raw_category.strip().title() if valid == lowered else valid
        return raw_category.strip()
    if lowered in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[lowered]
    # Fuzzy: check if any alias keyword appears in the raw string
    for alias_key, mapped in CATEGORY_ALIASES.items():
        if alias_key in lowered:
            return mapped
    return "Other"


def _normalize_amount(raw_amount: Any) -> Optional[Decimal]:
    """Strip currency symbols, commas; convert to Decimal."""
    if raw_amount is None:
        return None
    if isinstance(raw_amount, (int, float)):
        if raw_amount < 0:
            return None
        try:
            return Decimal(str(raw_amount)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return None
    if isinstance(raw_amount, str):
        # Remove currency symbols, commas, spaces
        cleaned = re.sub(r"[₹$€£¥,\s]", "", raw_amount.strip())
        # Handle parentheses for negative numbers
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1]
        try:
            amount = Decimal(cleaned).quantize(Decimal("0.01"))
            return amount if amount >= 0 else None
        except (InvalidOperation, ValueError):
            return None
    return None


def _build_prompt(raw_text: str) -> str:
    """Construct the extraction prompt for Gemini."""
    return (
        "Extract the invoice fields from the following raw invoice text. "
        "Return only valid JSON with keys: "
        "amount (number), currency (3-letter code or null), "
        "date (YYYY-MM-DD or null), vendor_name (string or null), "
        "category (one of: Travel, Supplies, Utilities, Professional Services, "
        "Food & Beverage, Rent, Insurance, Marketing, Software & SaaS, "
        "Hardware, Telecom, Maintenance, Other), "
        "confidence (0-1 float). "
        "If unsure about a field, set it to null. "
        "Do not output any extra text.\n\n"
        f"Raw text:\n<<<\n{raw_text[:6000]}\n>>>"
    )


def _rate_limit() -> None:
    """Enforce minimum interval between API calls."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """
    Robustly extract JSON from Gemini response.
    Handles: raw JSON, markdown code blocks, extra text around JSON.
    """
    cleaned = text.strip()

    # Attempt 1: Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Strip markdown code fences
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
    if md_match:
        try:
            return json.loads(md_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Attempt 3: Find first { ... last }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    return None


def _validate_response(data: Dict[str, Any]) -> ParsedInvoice:
    """Validate and normalize the AI response into ParsedInvoice."""
    amount = _normalize_amount(data.get("amount"))
    currency = data.get("currency", "INR")
    if not isinstance(currency, str) or len(currency) != 3:
        currency = "INR"

    date_str = data.get("date")
    if date_str:
        # Validate date format YYYY-MM-DD
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date_str)):
            date_str = None

    vendor_name = data.get("vendor_name")
    if vendor_name and not isinstance(vendor_name, str):
        vendor_name = str(vendor_name)

    raw_confidence = data.get("confidence", 0.0)
    try:
        confidence = float(raw_confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    category = _normalize_category(data.get("category"))

    return ParsedInvoice(
        amount=amount,
        currency=currency.upper(),
        date=date_str,
        vendor_name=vendor_name.strip() if vendor_name else None,
        category=category,
        confidence=confidence,
        raw_response=data,
        method="gemini",
    )


def parse_invoice(raw_text: str) -> AIServiceResult:
    """
    Main entry point — send raw invoice text to Gemini,
    return structured ParsedInvoice or error.

    Implements:
    - DEMO_MODE support (returns mock data without API calls)
    - Exponential backoff (max 3 retries)
    - Rate limiting (1 req/sec)
    - Strict JSON schema validation
    - Response normalization
    - Safe logging (hashed text, no raw content)
    """
    from invoices.middleware import hash_text_for_log

    if not raw_text or len(raw_text.strip()) < 10:
        return AIServiceResult(
            success=False,
            error="Raw text too short for parsing (minimum 10 characters).",
        )

    # Max input length guard
    max_len = getattr(settings, "MAX_RAW_TEXT_LENGTH", 50000)
    if len(raw_text) > max_len:
        return AIServiceResult(
            success=False,
            error=f"Raw text exceeds maximum length ({max_len} chars).",
        )

    text_hash = hash_text_for_log(raw_text)

    # ── DEMO MODE: return mock response without API call ───────
    if getattr(settings, "DEMO_MODE", False):
        logger.info("DEMO_MODE active — returning mock parse (text_hash=%s)", text_hash)
        return _demo_mode_response(raw_text)

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return AIServiceResult(
            success=False,
            error="GEMINI_API_KEY not configured. Set it in .env file.",
        )

    model_name = settings.GEMINI_MODEL
    max_retries = settings.AI_MAX_RETRIES
    prompt = _build_prompt(raw_text)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    last_error: Optional[str] = None
    start_time = time.time()

    for attempt in range(1, max_retries + 1):
        try:
            _rate_limit()

            logger.info(
                "Gemini request attempt %d/%d (model=%s, text_hash=%s, text_len=%d)",
                attempt, max_retries, model_name, text_hash, len(raw_text),
            )

            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=1024,
                ),
            )

            if not response or not response.text:
                last_error = f"Empty response from Gemini (attempt {attempt})"
                logger.warning(last_error)
                continue

            raw_response_text = response.text
            logger.debug("Gemini raw response: %s", raw_response_text[:500])

            parsed_json = _extract_json_from_response(raw_response_text)
            if parsed_json is None:
                last_error = f"Failed to extract JSON from response (attempt {attempt})"
                logger.warning(last_error)
                # On last attempt, don't retry
                if attempt < max_retries:
                    _backoff_sleep(attempt)
                continue

            # Validate required keys
            required_keys = {"amount", "confidence"}
            missing_keys = required_keys - set(parsed_json.keys())
            if missing_keys:
                last_error = f"Response missing keys: {missing_keys} (attempt {attempt})"
                logger.warning(last_error)
                if attempt < max_retries:
                    _backoff_sleep(attempt)
                continue

            parsed = _validate_response(parsed_json)
            latency = (time.time() - start_time) * 1000

            logger.info(
                "Gemini parse success: vendor=%s amount=%s confidence=%.2f latency=%.0fms",
                parsed.vendor_name, parsed.amount, parsed.confidence, latency,
            )

            return AIServiceResult(
                success=True,
                data=parsed,
                latency_ms=latency,
                attempts=attempt,
            )

        except genai.types.BlockedPromptException as e:
            last_error = f"Prompt blocked by safety filters: {e}"
            logger.error(last_error)
            break  # Don't retry — content issue

        except genai.types.StopCandidateException as e:
            last_error = f"Generation stopped unexpectedly: {e}"
            logger.warning(last_error)
            if attempt < max_retries:
                _backoff_sleep(attempt)

        except Exception as e:
            last_error = f"Gemini API error: {type(e).__name__}: {e}"
            logger.error(last_error, exc_info=True)
            if attempt < max_retries:
                _backoff_sleep(attempt)

    latency = (time.time() - start_time) * 1000
    return AIServiceResult(
        success=False,
        error=last_error or "All retry attempts exhausted.",
        latency_ms=latency,
        attempts=max_retries,
    )


def _backoff_sleep(attempt: int) -> None:
    """Exponential backoff: 2^attempt seconds (2s, 4s, 8s...)."""
    delay = min(2 ** attempt, 30)
    logger.info("Backing off for %ds before retry...", delay)
    time.sleep(delay)


def _demo_mode_response(raw_text: str) -> AIServiceResult:
    """
    Return a mock/fallback-based parse response without calling Gemini.
    Uses the fallback parser to provide realistic-looking data for demos.
    Zero API cost.
    """
    from invoices.services.fallback_parser import parse_invoice_fallback

    start = time.time()
    fallback = parse_invoice_fallback(raw_text)

    parsed = ParsedInvoice(
        amount=fallback.amount,
        currency=fallback.currency if hasattr(fallback, "currency") else "INR",
        date=fallback.date,
        vendor_name=fallback.vendor_name,
        category=fallback.category,
        confidence=min(fallback.confidence + 0.3, 0.95) if fallback.confidence else 0.75,
        raw_response={"demo_mode": True, "method": "fallback+boost"},
        method="demo",
    )

    return AIServiceResult(
        success=fallback.is_valid,
        data=parsed if fallback.is_valid else None,
        error=None if fallback.is_valid else "Demo mode: fallback parser found no valid data.",
        latency_ms=(time.time() - start) * 1000,
        attempts=0,
    )
