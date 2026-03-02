"""
FinVibe — Invoice processing orchestrator.
Manages the AI parse → fallback → save chain with
idempotency, audit logging, and atomic operations.
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from invoices.models import AuditLog, Invoice
from invoices.services.ai_service import AIServiceResult, parse_invoice
from invoices.services.fallback_parser import FallbackResult, parse_invoice_fallback

logger = logging.getLogger("invoices")


def process_invoice(
    invoice: Invoice,
    actor: str = "system",
    force_reparse: bool = False,
    overwrite_fields: bool = False,
) -> Tuple[bool, str]:
    """
    Parse raw_text and populate invoice fields.

    Flow:
    1. Idempotency check (skip if already parsed and not forced)
    2. AI extraction via Gemini
    3. If AI fails or low confidence → fallback parser
    4. Populate model fields
    5. Audit log entry

    Args:
        invoice: Invoice instance with raw_text populated.
        actor: Username triggering the parse.
        force_reparse: If True, reparse even if already parsed.
        overwrite_fields: If True, overwrite existing non-empty fields.

    Returns:
        (success: bool, message: str)
    """
    # ── Sanity checks ───────────────────────────────────────────────
    if not invoice.raw_text or len(invoice.raw_text.strip()) < 10:
        return False, "Raw text is too short for parsing (minimum 10 characters)."

    # ── Idempotency guard ───────────────────────────────────────────
    if invoice.parsed_by_ai and not force_reparse:
        if invoice.parsed_attempts > 0:
            logger.info(
                "Invoice %s already parsed (attempts=%d), skipping.",
                invoice.short_id, invoice.parsed_attempts,
            )
            return True, "Already parsed. Use force_reparse to re-process."

    # ── Increment attempt counter ───────────────────────────────────
    invoice.parsed_attempts += 1

    # ── Step 1: Try AI extraction ───────────────────────────────────
    ai_result: Optional[AIServiceResult] = None
    used_ai = False
    confidence_threshold = settings.AI_CONFIDENCE_THRESHOLD

    try:
        ai_result = parse_invoice(invoice.raw_text)
    except Exception as e:
        error_msg = f"AI service exception: {type(e).__name__}: {e}"
        logger.error(error_msg, exc_info=True)
        invoice.parsing_error = error_msg
        ai_result = AIServiceResult(success=False, error=error_msg)

    # ── Step 2: Evaluate AI result ──────────────────────────────────
    if ai_result and ai_result.success and ai_result.data:
        parsed = ai_result.data
        if parsed.confidence >= confidence_threshold:
            # AI result is good — apply fields
            _apply_parsed_fields(
                invoice, parsed.amount, parsed.date, parsed.vendor_name,
                parsed.category, parsed.currency, overwrite_fields,
            )
            invoice.parsed_by_ai = True
            invoice.ai_confidence = parsed.confidence
            invoice.ai_response = parsed.raw_response
            invoice.parsed_at = timezone.now()
            invoice.parsing_error = ""
            used_ai = True

            logger.info(
                "AI parse success for invoice %s: confidence=%.2f vendor=%s amount=%s",
                invoice.short_id, parsed.confidence, parsed.vendor_name, parsed.amount,
            )
        else:
            # AI returned but confidence too low — will try fallback
            logger.info(
                "AI confidence too low (%.2f < %.2f) for invoice %s, trying fallback.",
                parsed.confidence, confidence_threshold, invoice.short_id,
            )
            invoice.ai_response = parsed.raw_response
            invoice.ai_confidence = parsed.confidence

    # ── Step 3: Fallback if AI failed or low confidence ─────────────
    if not used_ai:
        fallback_result = parse_invoice_fallback(invoice.raw_text)

        if fallback_result.is_valid:
            _apply_parsed_fields(
                invoice, fallback_result.amount, fallback_result.date,
                fallback_result.vendor_name, fallback_result.category,
                "INR", overwrite_fields,
            )
            invoice.parsed_by_ai = False
            invoice.ai_confidence = fallback_result.confidence
            invoice.parsed_at = timezone.now()

            if not invoice.ai_response:
                invoice.ai_response = {
                    "method": "fallback",
                    "patterns": fallback_result.matched_patterns,
                }

            logger.info(
                "Fallback parse for invoice %s: amount=%s vendor=%s",
                invoice.short_id, fallback_result.amount, fallback_result.vendor_name,
            )
        else:
            # Both AI and fallback failed
            error = ai_result.error if ai_result else "AI service not called"
            invoice.parsing_error = f"All parsing methods failed. AI: {error}. Fallback: no amount found."
            logger.warning("All parsing failed for invoice %s", invoice.short_id)

    # ── Step 4: Save and audit ──────────────────────────────────────
    with transaction.atomic():
        invoice.save()

        if used_ai:
            action = AuditLog.ActionChoices.AI_PARSED
            details = {
                "confidence": invoice.ai_confidence,
                "vendor": invoice.vendor_name,
                "amount": str(invoice.amount),
                "category": invoice.category,
                "latency_ms": ai_result.latency_ms if ai_result else 0,
                "attempts": ai_result.attempts if ai_result else 0,
            }
        elif invoice.parsed_at:
            action = AuditLog.ActionChoices.FALLBACK_PARSED
            details = {
                "confidence": invoice.ai_confidence,
                "vendor": invoice.vendor_name,
                "amount": str(invoice.amount),
                "category": invoice.category,
            }
        else:
            action = AuditLog.ActionChoices.AI_FAILED
            details = {
                "error": invoice.parsing_error,
                "ai_confidence": invoice.ai_confidence,
            }

        if force_reparse:
            AuditLog.objects.create(
                invoice=invoice,
                action=AuditLog.ActionChoices.REPARSE_TRIGGERED,
                actor=actor,
                details={"reason": "Manual re-parse triggered"},
            )

        AuditLog.objects.create(
            invoice=invoice,
            action=action,
            actor=actor,
            details=details,
        )

    # ── Return result ───────────────────────────────────────────────
    if used_ai:
        return True, f"AI parsed successfully (confidence: {invoice.ai_confidence:.0%})"
    elif invoice.parsed_at:
        return True, f"Fallback parsed (confidence: {invoice.ai_confidence:.0%}). Review recommended."
    else:
        return False, invoice.parsing_error


def _apply_parsed_fields(
    invoice: Invoice,
    amount: Optional[Decimal],
    date_str: Optional[str],
    vendor_name: Optional[str],
    category: Optional[str],
    currency: str,
    overwrite: bool,
) -> None:
    """Apply parsed values to invoice fields if empty or overwrite=True."""
    if amount is not None and (overwrite or invoice.amount == Decimal("0.00")):
        invoice.amount = amount

    if date_str and (overwrite or invoice.date is None):
        try:
            invoice.date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.warning("Invalid date format: %s", date_str)

    if vendor_name and (overwrite or not invoice.vendor_name):
        invoice.vendor_name = vendor_name[:255]

    if category and category != "Other" and (overwrite or invoice.category == "Other"):
        invoice.category = category

    if currency and (overwrite or invoice.currency == "INR"):
        invoice.currency = currency.upper()[:3]
