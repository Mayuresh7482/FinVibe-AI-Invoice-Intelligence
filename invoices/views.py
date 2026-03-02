"""
FinVibe — Views for the invoice dashboard.
Handles: list (with search, filter, pagination), create, detail/edit, delete, re-parse.
"""
import logging
from decimal import Decimal
from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from invoices.forms import InvoiceForm, InvoiceSearchForm
from invoices.models import AuditLog, Invoice
from invoices.services.invoice_processor import process_invoice

logger = logging.getLogger("invoices")


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard — paginated invoice list with search, filters, and summary stats.
    """
    form = InvoiceSearchForm(request.GET)
    queryset = Invoice.objects.all()

    # ── Apply filters ───────────────────────────────────────────────
    if form.is_valid():
        q = form.cleaned_data.get("q")
        if q:
            queryset = queryset.filter(vendor_name__icontains=q)

        category = form.cleaned_data.get("category")
        if category:
            queryset = queryset.filter(category=category)

        date_from = form.cleaned_data.get("date_from")
        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        date_to = form.cleaned_data.get("date_to")
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        parsed = form.cleaned_data.get("parsed")
        if parsed == "ai":
            queryset = queryset.filter(parsed_by_ai=True)
        elif parsed == "manual":
            queryset = queryset.filter(parsed_by_ai=False)

    # ── Summary stats (for filtered results) ────────────────────────
    stats = queryset.aggregate(
        total_spent=Sum("amount"),
        invoice_count=Count("id"),
        avg_confidence=Avg("ai_confidence"),
        ai_parsed_count=Count("id", filter=Q(parsed_by_ai=True)),
    )
    stats["total_spent"] = stats["total_spent"] or Decimal("0.00")
    stats["avg_confidence"] = stats["avg_confidence"] or 0.0
    stats["manual_count"] = stats["invoice_count"] - stats["ai_parsed_count"]

    # ── Pagination ──────────────────────────────────────────────────
    paginator = Paginator(queryset, 15)
    page = request.GET.get("page")
    try:
        invoices = paginator.page(page)
    except PageNotAnInteger:
        invoices = paginator.page(1)
    except EmptyPage:
        invoices = paginator.page(paginator.num_pages)

    context: Dict[str, Any] = {
        "invoices": invoices,
        "form": form,
        "stats": stats,
        "page_title": "Dashboard",
    }
    return render(request, "invoices/dashboard.html", context)


@login_required
def invoice_create(request: HttpRequest) -> HttpResponse:
    """Create a new invoice — paste raw text, save triggers AI parse."""
    if request.method == "POST":
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.save()

            # Log creation
            AuditLog.objects.create(
                invoice=invoice,
                action=AuditLog.ActionChoices.CREATED,
                actor=request.user.username or "admin",
                details={"method": "dashboard_form"},
            )

            # Trigger AI parsing
            if invoice.raw_text:
                success, message = process_invoice(
                    invoice=invoice,
                    actor=request.user.username or "admin",
                    force_reparse=form.cleaned_data.get("force_reparse", False),
                )
                if success:
                    messages.success(request, f"✅ Invoice created & parsed: {message}")
                else:
                    messages.warning(request, f"⚠️ Invoice saved but parsing had issues: {message}")
            else:
                messages.success(request, "Invoice created (no raw text for parsing).")

            return redirect("invoice_detail", pk=invoice.pk)
    else:
        form = InvoiceForm()

    return render(request, "invoices/invoice_form.html", {
        "form": form,
        "page_title": "New Invoice",
        "is_edit": False,
    })


@login_required
def invoice_detail(request: HttpRequest, pk: str) -> HttpResponse:
    """View invoice detail with AI metadata and audit trail."""
    invoice = get_object_or_404(Invoice, pk=pk)
    audit_logs = invoice.audit_logs.all()[:20]

    if request.method == "POST":
        form = InvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            old_values = {
                "vendor_name": invoice.vendor_name,
                "amount": str(invoice.amount),
                "category": invoice.category,
                "date": str(invoice.date),
            }
            invoice = form.save()

            new_values = {
                "vendor_name": invoice.vendor_name,
                "amount": str(invoice.amount),
                "category": invoice.category,
                "date": str(invoice.date),
            }

            # Log manual edit
            changed_fields = {
                k: {"old": old_values[k], "new": new_values[k]}
                for k in old_values if old_values[k] != new_values[k]
            }
            if changed_fields:
                AuditLog.objects.create(
                    invoice=invoice,
                    action=AuditLog.ActionChoices.MANUAL_EDIT,
                    actor=request.user.username or "admin",
                    details={"changed": changed_fields},
                )

            messages.success(request, "✅ Invoice updated successfully.")
            return redirect("invoice_detail", pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)

    return render(request, "invoices/invoice_detail.html", {
        "invoice": invoice,
        "form": form,
        "audit_logs": audit_logs,
        "page_title": f"Invoice #{invoice.short_id}",
    })


@login_required
@require_POST
def invoice_reparse(request: HttpRequest, pk: str) -> HttpResponse:
    """Force re-parse an invoice with AI."""
    invoice = get_object_or_404(Invoice, pk=pk)
    actor = request.user.username or "admin"

    success, message = process_invoice(
        invoice=invoice,
        actor=actor,
        force_reparse=True,
        overwrite_fields=True,
    )

    if success:
        messages.success(request, f"✅ Re-parsed: {message}")
    else:
        messages.error(request, f"❌ Re-parse failed: {message}")

    return redirect("invoice_detail", pk=invoice.pk)


@login_required
@require_POST
def invoice_delete(request: HttpRequest, pk: str) -> HttpResponse:
    """Delete an invoice with audit trail."""
    invoice = get_object_or_404(Invoice, pk=pk)
    short_id = invoice.short_id
    vendor = invoice.vendor_name

    # Log deletion before destroying
    AuditLog.objects.create(
        invoice=invoice,
        action=AuditLog.ActionChoices.DELETED,
        actor=request.user.username or "admin",
        details={"vendor": vendor, "amount": str(invoice.amount)},
    )

    invoice.delete()
    messages.success(request, f"🗑️ Invoice #{short_id} ({vendor}) deleted.")
    return redirect("dashboard")


@login_required
@require_POST
def invoice_accept_ai(request: HttpRequest, pk: str) -> HttpResponse:
    """Accept AI-parsed values (mark as reviewed)."""
    invoice = get_object_or_404(Invoice, pk=pk)
    AuditLog.objects.create(
        invoice=invoice,
        action=AuditLog.ActionChoices.AI_ACCEPTED,
        actor=request.user.username or "admin",
        details={
            "confidence": invoice.ai_confidence,
            "vendor": invoice.vendor_name,
            "amount": str(invoice.amount),
        },
    )
    messages.success(request, "✅ AI values accepted.")
    return redirect("invoice_detail", pk=invoice.pk)


@login_required
@require_POST
def invoice_reject_ai(request: HttpRequest, pk: str) -> HttpResponse:
    """Reject AI-parsed values (clear AI fields)."""
    invoice = get_object_or_404(Invoice, pk=pk)
    invoice.parsed_by_ai = False
    invoice.ai_confidence = None
    invoice.amount = Decimal("0.00")
    invoice.vendor_name = ""
    invoice.category = "Other"
    invoice.date = None
    invoice.save()

    AuditLog.objects.create(
        invoice=invoice,
        action=AuditLog.ActionChoices.AI_REJECTED,
        actor=request.user.username or "admin",
        details={"reason": "Admin rejected AI values"},
    )
    messages.info(request, "AI values rejected. Please fill fields manually.")
    return redirect("invoice_detail", pk=invoice.pk)


def api_parse_preview(request: HttpRequest) -> JsonResponse:
    """
    AJAX endpoint — preview AI parsing without saving.
    POST { "raw_text": "..." } → returns parsed fields.
    Respects DEMO_MODE: if enabled, returns mock data.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    import json
    from django.conf import settings as conf

    try:
        body = json.loads(request.body)
        raw_text = body.get("raw_text", "")
    except (json.JSONDecodeError, AttributeError):
        raw_text = request.POST.get("raw_text", "")

    if not raw_text or len(raw_text.strip()) < 10:
        return JsonResponse({"error": "Raw text too short (min 10 chars)"}, status=400)

    # Input length guard
    max_len = getattr(conf, "MAX_RAW_TEXT_LENGTH", 50000)
    if len(raw_text) > max_len:
        return JsonResponse(
            {"error": f"Text too long. Max {max_len} characters allowed."},
            status=400,
        )

    # Quick parse without saving
    from invoices.services.ai_service import parse_invoice as ai_parse
    from invoices.services.fallback_parser import parse_invoice_fallback

    ai_result = ai_parse(raw_text)
    if ai_result.success and ai_result.data:
        return JsonResponse({
            "success": True,
            "method": ai_result.data.method,
            "data": {
                "vendor_name": ai_result.data.vendor_name,
                "amount": str(ai_result.data.amount) if ai_result.data.amount else None,
                "date": ai_result.data.date,
                "category": ai_result.data.category,
                "currency": ai_result.data.currency,
                "confidence": ai_result.data.confidence,
            },
            "latency_ms": round(ai_result.latency_ms, 1),
        })

    # Fallback
    fb = parse_invoice_fallback(raw_text)
    return JsonResponse({
        "success": fb.is_valid,
        "method": "fallback",
        "data": {
            "vendor_name": fb.vendor_name,
            "amount": str(fb.amount) if fb.amount else None,
            "date": fb.date,
            "category": fb.category,
            "confidence": fb.confidence,
        },
    })


def api_demo_parse(request: HttpRequest) -> JsonResponse:
    """
    Demo-only parse endpoint — always uses demo mode (no Gemini API calls).
    Used by the demo popup to avoid production quota consumption.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    import json
    from invoices.services.ai_service import _demo_mode_response

    try:
        body = json.loads(request.body)
        raw_text = body.get("raw_text", "")
    except (json.JSONDecodeError, AttributeError):
        raw_text = request.POST.get("raw_text", "")

    if not raw_text or len(raw_text.strip()) < 10:
        return JsonResponse({"error": "Raw text too short (min 10 chars)"}, status=400)

    result = _demo_mode_response(raw_text)

    if result.success and result.data:
        return JsonResponse({
            "success": True,
            "method": "demo",
            "data": {
                "vendor_name": result.data.vendor_name,
                "amount": str(result.data.amount) if result.data.amount else None,
                "date": result.data.date,
                "category": result.data.category,
                "currency": result.data.currency,
                "confidence": result.data.confidence,
            },
            "latency_ms": round(result.latency_ms, 1),
        })

    return JsonResponse({
        "success": False,
        "method": "demo",
        "data": None,
        "error": result.error or "Demo parse failed.",
    })
