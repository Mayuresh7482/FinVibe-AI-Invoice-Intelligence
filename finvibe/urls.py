"""
FinVibe — Root URL configuration.
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def healthz(request):
    """Health-check endpoint for load balancers and monitoring."""
    return JsonResponse({"status": "ok", "service": "finvibe"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("invoices.urls")),
    path("healthz/", healthz, name="healthz"),
]

# ─── Admin site branding ──────────────────────────────────────────
admin.site.site_header = "FinVibe • AI Invoice Automator"
admin.site.site_title = "FinVibe Admin"
admin.site.index_title = "Invoice Management"
