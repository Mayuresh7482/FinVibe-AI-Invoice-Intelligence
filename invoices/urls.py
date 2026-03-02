"""
FinVibe — Invoice URL patterns.
"""
from django.urls import path
from invoices import views

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),

    # CRUD
    path("invoice/new/", views.invoice_create, name="invoice_create"),
    path("invoice/<str:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoice/<str:pk>/delete/", views.invoice_delete, name="invoice_delete"),

    # AI actions
    path("invoice/<str:pk>/reparse/", views.invoice_reparse, name="invoice_reparse"),
    path("invoice/<str:pk>/accept-ai/", views.invoice_accept_ai, name="invoice_accept_ai"),
    path("invoice/<str:pk>/reject-ai/", views.invoice_reject_ai, name="invoice_reject_ai"),

    # API
    path("api/parse-preview/", views.api_parse_preview, name="api_parse_preview"),
    path("api/demo-parse/", views.api_demo_parse, name="api_demo_parse"),
]
