"""
FinVibe — Deterministic fallback parser.
Extracts amount, date, vendor_name, and category from raw invoice text
using regex patterns and keyword heuristics when AI fails or has low confidence.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

logger = logging.getLogger("invoices")


@dataclass
class FallbackResult:
    """Result from deterministic parsing."""
    amount: Optional[Decimal] = None
    date: Optional[str] = None
    vendor_name: Optional[str] = None
    category: str = "Other"
    confidence: float = 0.40
    method: str = "fallback"
    matched_patterns: List[str] = None

    def __post_init__(self):
        if self.matched_patterns is None:
            self.matched_patterns = []

    @property
    def is_valid(self) -> bool:
        return self.amount is not None


# ─── Amount extraction ─────────────────────────────────────────────

# Patterns for total/amount lines
_AMOUNT_KEYWORDS = [
    r"(?:grand\s*)?total\s*(?:amount)?",
    r"amount\s*(?:due|payable|total)?",
    r"balance\s*due",
    r"net\s*(?:amount|payable|total)",
    r"invoice\s*(?:amount|total)",
    r"sum\s*total",
    r"total\s*due",
    r"pay(?:able)?\s*amount",
]

# Currency symbols and their patterns
_CURRENCY_PATTERN = r"[₹$€£¥]"
_NUMBER_PATTERN = r"[\d,]+\.?\d*"


def _extract_amount(text: str) -> Tuple[Optional[Decimal], List[str]]:
    """
    Extract the most likely total amount from invoice text.
    Strategy:
    1. Look for amounts near keywords like "Total", "Amount Due"
    2. Look for currency symbol + number patterns
    3. Pick the largest amount found near keywords
    """
    matches: List[Tuple[Decimal, str]] = []

    # Strategy 1: Amount near keywords
    for kw in _AMOUNT_KEYWORDS:
        pattern = (
            rf"(?i){kw}\s*[:=\-]?\s*"
            rf"(?:{_CURRENCY_PATTERN}\s*)?"
            rf"({_NUMBER_PATTERN})"
        )
        for m in re.finditer(pattern, text):
            amount = _parse_number(m.group(1))
            if amount is not None and amount > Decimal("0"):
                matches.append((amount, f"keyword:{kw.split('(')[0].strip()}"))

    # Strategy 2: Currency symbol followed by number
    currency_pattern = rf"({_CURRENCY_PATTERN})\s*({_NUMBER_PATTERN})"
    for m in re.finditer(currency_pattern, text):
        amount = _parse_number(m.group(2))
        if amount is not None and amount > Decimal("0"):
            matches.append((amount, f"currency:{m.group(1)}"))

    # Strategy 3: "Rs." or "INR" patterns
    rs_pattern = rf"(?i)(?:Rs\.?|INR)\s*({_NUMBER_PATTERN})"
    for m in re.finditer(rs_pattern, text):
        amount = _parse_number(m.group(1))
        if amount is not None and amount > Decimal("0"):
            matches.append((amount, "currency:Rs/INR"))

    if not matches:
        return None, []

    # Pick the largest amount found near a keyword,
    # or the largest overall if no keyword matches
    keyword_matches = [(a, p) for a, p in matches if p.startswith("keyword:")]
    if keyword_matches:
        best = max(keyword_matches, key=lambda x: x[0])
    else:
        best = max(matches, key=lambda x: x[0])

    patterns_used = list(set(p for _, p in matches))
    return best[0], patterns_used


def _parse_number(raw: str) -> Optional[Decimal]:
    """Convert a raw number string (possibly with commas) to Decimal."""
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        d = Decimal(cleaned).quantize(Decimal("0.01"))
        return d if d >= 0 else None
    except (InvalidOperation, ValueError):
        return None


# ─── Date extraction ───────────────────────────────────────────────

# Common date formats
_DATE_PATTERNS = [
    # YYYY-MM-DD
    (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
    # DD/MM/YYYY or DD-MM-YYYY
    (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", "dmy"),
    # MM/DD/YYYY
    (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", "mdy"),
    # DD Mon YYYY (e.g., 15 Jan 2024)
    (r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})", "dmy_text"),
    # Mon DD, YYYY (e.g., January 15, 2024)
    (r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})", "mdy_text"),
]

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_KEYWORDS = [
    r"(?i)(?:invoice\s*)?date",
    r"(?i)dated?",
    r"(?i)bill\s*date",
]


def _extract_date(text: str) -> Optional[str]:
    """
    Extract the most likely invoice date.
    Prefers dates near "Date:" keyword; falls back to first date found.
    """
    # First, look near date keywords
    for kw in _DATE_KEYWORDS:
        pattern = rf"{kw}\s*[:=\-]?\s*(.{{1,30}})"
        m = re.search(pattern, text)
        if m:
            date_region = m.group(1).strip()
            parsed = _try_parse_date(date_region)
            if parsed:
                return parsed

    # Fallback: find any date in the text
    for line in text.split("\n"):
        parsed = _try_parse_date(line)
        if parsed:
            return parsed

    return None


def _try_parse_date(text: str) -> Optional[str]:
    """Try to parse a date from a text snippet, return YYYY-MM-DD or None."""
    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Heuristic: if first number > 12, it's DD; otherwise try DD/MM first
        if d > 12 and mo <= 12:
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                pass
        elif mo > 12 and d <= 12:
            # Likely MM/DD/YYYY
            try:
                return datetime(y, d, mo).strftime("%Y-%m-%d")
            except ValueError:
                pass
        else:
            # Assume DD/MM/YYYY (Indian format)
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                pass

    # DD Mon YYYY
    m = re.search(
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        d, mon, y = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
        mo = _MONTH_MAP.get(mon)
        if mo:
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                pass

    # Mon DD, YYYY
    m = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        mon, d, y = m.group(1).lower()[:3], int(m.group(2)), int(m.group(3))
        mo = _MONTH_MAP.get(mon)
        if mo:
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                pass

    return None


# ─── Vendor extraction ─────────────────────────────────────────────

_VENDOR_KEYWORDS = [
    r"(?i)(?:from|vendor|supplier|billed?\s*by|sold\s*by|company)\s*[:=\-]?\s*(.+)",
]


def _extract_vendor(text: str) -> Optional[str]:
    """
    Extract vendor name using keyword patterns.
    Falls back to first line of text if no keyword match.
    """
    for pattern in _VENDOR_KEYWORDS:
        m = re.search(pattern, text)
        if m:
            vendor = m.group(1).strip()
            # Clean up: take first line, remove trailing punctuation
            vendor = vendor.split("\n")[0].strip().rstrip(".,;:")
            if 2 <= len(vendor) <= 200:
                return vendor

    # Fallback: first non-empty line that looks like a company name
    for line in text.split("\n")[:10]:
        line = line.strip()
        if (
            line
            and 3 <= len(line) <= 100
            and not re.match(r"^[\d\s\-/.,]+$", line)  # Not purely numbers/punctuation
            and not re.match(r"(?i)^(invoice|bill|receipt|tax|date|total|amount)", line)
        ):
            return line

    return None


# ─── Category extraction ──────────────────────────────────────────

_CATEGORY_KEYWORD_MAP = {
    "Travel": [
        "flight", "airline", "hotel", "travel", "uber", "ola", "cab",
        "taxi", "bus", "train", "railway", "booking", "airbnb", "makemytrip",
    ],
    "Supplies": [
        "office", "supplies", "stationery", "paper", "ink", "toner",
        "pen", "notebook", "printer",
    ],
    "Utilities": [
        "electricity", "power", "water", "gas", "sewage", "municipal",
        "utility", "bill",
    ],
    "Food & Beverage": [
        "food", "restaurant", "meal", "catering", "lunch", "dinner",
        "breakfast", "coffee", "beverage", "swiggy", "zomato",
    ],
    "Rent": ["rent", "lease", "property", "office space"],
    "Insurance": ["insurance", "policy", "premium", "coverage"],
    "Marketing": [
        "marketing", "advertising", "ad ", "ads", "campaign",
        "promotion", "google ads", "facebook", "social media",
    ],
    "Software & SaaS": [
        "software", "saas", "subscription", "license", "cloud",
        "aws", "azure", "gcp", "hosting", "domain",
    ],
    "Hardware": [
        "hardware", "laptop", "computer", "monitor", "keyboard",
        "mouse", "server", "equipment",
    ],
    "Telecom": [
        "telecom", "phone", "mobile", "internet", "broadband",
        "data plan", "jio", "airtel", "vodafone", "sim",
    ],
    "Maintenance": [
        "maintenance", "repair", "cleaning", "service", "amc",
        "annual maintenance",
    ],
    "Professional Services": [
        "consulting", "legal", "accounting", "audit", "advisory",
        "professional", "lawyer", "advocate", "chartered accountant",
    ],
}


def _extract_category(text: str) -> str:
    """
    Classify invoice category based on keyword frequency.
    Returns the category with the most keyword hits.
    """
    text_lower = text.lower()
    scores: dict = {}

    for category, keywords in _CATEGORY_KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[category] = score

    if scores:
        return max(scores, key=scores.get)
    return "Other"


# ─── Main entry point ─────────────────────────────────────────────

def parse_invoice_fallback(raw_text: str) -> FallbackResult:
    """
    Deterministic fallback parser — extract amount, date, vendor, category
    from raw invoice text using regex patterns and keyword heuristics.

    Returns FallbackResult with confidence fixed at 0.40 (fallback baseline).
    """
    if not raw_text or len(raw_text.strip()) < 5:
        logger.warning("Fallback parser: raw_text too short")
        return FallbackResult()

    logger.info("Running fallback parser on %d chars of text", len(raw_text))

    amount, patterns_used = _extract_amount(raw_text)
    date_str = _extract_date(raw_text)
    vendor_name = _extract_vendor(raw_text)
    category = _extract_category(raw_text)

    # Adjust confidence based on how many fields we extracted
    fields_found = sum([
        amount is not None,
        date_str is not None,
        vendor_name is not None,
        category != "Other",
    ])
    confidence = 0.20 + (fields_found * 0.05)  # 0.20 – 0.40

    result = FallbackResult(
        amount=amount,
        date=date_str,
        vendor_name=vendor_name,
        category=category,
        confidence=round(confidence, 2),
        method="fallback",
        matched_patterns=patterns_used,
    )

    logger.info(
        "Fallback result: amount=%s date=%s vendor=%s category=%s confidence=%.2f",
        result.amount, result.date, result.vendor_name, result.category, result.confidence,
    )

    return result
