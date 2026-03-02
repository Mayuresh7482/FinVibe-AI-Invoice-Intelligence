"""
FinVibe — Rate limiting middleware + security utilities.
Implements per-IP sliding-window rate limiting for all endpoints,
with stricter limits on the parse endpoint.
"""
import hashlib
import logging
import time
from collections import defaultdict
from threading import Lock
from typing import Callable, Dict, List, Tuple

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

logger = logging.getLogger("invoices")


class RateLimitMiddleware:
    """
    Sliding-window rate limiter per IP address.
    - General endpoints: RATE_LIMIT_PER_MINUTE requests/min
    - Parse endpoints: RATE_LIMIT_PARSE_PER_MINUTE requests/min
    """

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response
        self._general_windows: Dict[str, List[float]] = defaultdict(list)
        self._parse_windows: Dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()
        self._general_limit = getattr(settings, "RATE_LIMIT_PER_MINUTE", 30)
        self._parse_limit = getattr(settings, "RATE_LIMIT_PARSE_PER_MINUTE", 5)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        client_ip = self._get_client_ip(request)
        now = time.time()
        path = request.path.lower()

        # Check parse-specific rate limit
        is_parse_endpoint = (
            "/api/parse-preview/" in path
            or "/reparse/" in path
            or (request.method == "POST" and "/invoice/new/" in path)
        )

        with self._lock:
            # General rate limit
            self._cleanup_window(self._general_windows, client_ip, now)
            if len(self._general_windows[client_ip]) >= self._general_limit:
                logger.warning(
                    "Rate limit exceeded (general) for IP %s: %d/%d req/min",
                    self._mask_ip(client_ip),
                    len(self._general_windows[client_ip]),
                    self._general_limit,
                )
                return JsonResponse(
                    {"error": "Rate limit exceeded. Please try again later."},
                    status=429,
                )
            self._general_windows[client_ip].append(now)

            # Parse-specific rate limit
            if is_parse_endpoint:
                self._cleanup_window(self._parse_windows, client_ip, now)
                if len(self._parse_windows[client_ip]) >= self._parse_limit:
                    logger.warning(
                        "Rate limit exceeded (parse) for IP %s: %d/%d req/min",
                        self._mask_ip(client_ip),
                        len(self._parse_windows[client_ip]),
                        self._parse_limit,
                    )
                    return JsonResponse(
                        {"error": "Parse rate limit exceeded. Max {} parses/min.".format(
                            self._parse_limit
                        )},
                        status=429,
                    )
                self._parse_windows[client_ip].append(now)

        return self.get_response(request)

    @staticmethod
    def _get_client_ip(request: HttpRequest) -> str:
        """Get client IP, checking X-Forwarded-For for proxy setups."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    @staticmethod
    def _mask_ip(ip: str) -> str:
        """Mask IP for safe logging (show first 2 octets only)."""
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.x"
        return ip[:8] + "..."

    @staticmethod
    def _cleanup_window(
        windows: Dict[str, List[float]], key: str, now: float
    ) -> None:
        """Remove timestamps older than 60 seconds."""
        cutoff = now - 60.0
        windows[key] = [t for t in windows[key] if t > cutoff]


# ─── Logging Safety Utilities ──────────────────────────────────────

def hash_text_for_log(text: str) -> str:
    """Return SHA-256 hash of text for safe logging (never log raw text)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def mask_api_key(key: str) -> str:
    """Mask API key — show first 4 and last 4 chars only."""
    if not key or len(key) < 10:
        return "***"
    return f"{key[:4]}...{key[-4:]}"
