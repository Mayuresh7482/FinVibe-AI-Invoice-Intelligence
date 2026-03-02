"""
FinVibe — Tests for views (dashboard, CRUD, API).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from invoices.models import Invoice


class DashboardViewTest(TestCase):
    """Test the dashboard view."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testadmin", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="testadmin", password="testpass123")

        for i in range(20):
            Invoice.objects.create(
                vendor_name=f"Vendor {i}",
                raw_text=f"Test invoice raw text content {i}",
                amount=Decimal(f"{(i + 1) * 1000}.00"),
                category="Supplies" if i % 2 == 0 else "Travel",
            )

    def test_dashboard_requires_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_loads(self) -> None:
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_dashboard_pagination(self) -> None:
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["invoices"].has_other_pages)

    def test_dashboard_search(self) -> None:
        response = self.client.get(reverse("dashboard"), {"q": "Vendor 5"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vendor 5")

    def test_dashboard_category_filter(self) -> None:
        response = self.client.get(reverse("dashboard"), {"category": "Travel"})
        self.assertEqual(response.status_code, 200)

    def test_dashboard_stats(self) -> None:
        response = self.client.get(reverse("dashboard"))
        stats = response.context["stats"]
        self.assertEqual(stats["invoice_count"], 20)
        self.assertGreater(stats["total_spent"], Decimal("0"))


class InvoiceCreateViewTest(TestCase):
    """Test invoice creation."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testadmin", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="testadmin", password="testpass123")

    def test_create_page_loads(self) -> None:
        response = self.client.get(reverse("invoice_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Invoice")

    def test_create_invoice_success(self) -> None:
        response = self.client.post(reverse("invoice_create"), {
            "raw_text": "Test invoice with enough content for parsing validation",
            "vendor_name": "New Test Vendor",
            "amount": "5000.00",
            "category": "Supplies",
            "currency": "INR",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_create_invoice_empty_raw_text(self) -> None:
        """Form should reject empty raw_text (it's required)."""
        response = self.client.post(reverse("invoice_create"), {
            "raw_text": "",
            "vendor_name": "Test",
            "amount": "100.00",
            "category": "Other",
            "currency": "INR",
        })
        self.assertEqual(response.status_code, 200)  # Re-renders form with errors
        self.assertEqual(Invoice.objects.count(), 0)


class InvoiceDetailViewTest(TestCase):
    """Test invoice detail/edit view."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testadmin", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="testadmin", password="testpass123")
        self.invoice = Invoice.objects.create(
            vendor_name="Detail Test Vendor",
            raw_text="Detail test invoice raw text content here",
            amount=Decimal("7500.00"),
            category="Utilities",
        )

    def test_detail_page_loads(self) -> None:
        response = self.client.get(
            reverse("invoice_detail", kwargs={"pk": self.invoice.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Test Vendor")

    def test_detail_shows_audit_trail(self) -> None:
        response = self.client.get(
            reverse("invoice_detail", kwargs={"pk": self.invoice.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Audit Trail")

    def test_update_invoice(self) -> None:
        response = self.client.post(
            reverse("invoice_detail", kwargs={"pk": self.invoice.pk}),
            {
                "raw_text": "Updated raw text with enough content for validation",
                "vendor_name": "Updated Vendor",
                "amount": "9000.00",
                "category": "Travel",
                "currency": "INR",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.vendor_name, "Updated Vendor")
        self.assertEqual(self.invoice.amount, Decimal("9000.00"))

    def test_404_for_invalid_pk(self) -> None:
        response = self.client.get(
            reverse("invoice_detail", kwargs={"pk": "00000000-0000-0000-0000-000000000000"})
        )
        self.assertEqual(response.status_code, 404)


class InvoiceDeleteViewTest(TestCase):
    """Test invoice deletion."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testadmin", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="testadmin", password="testpass123")
        self.invoice = Invoice.objects.create(
            vendor_name="Delete Test",
            raw_text="This invoice will be deleted as part of testing",
        )

    def test_delete_invoice(self) -> None:
        response = self.client.post(
            reverse("invoice_delete", kwargs={"pk": self.invoice.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_delete_requires_post(self) -> None:
        response = self.client.get(
            reverse("invoice_delete", kwargs={"pk": self.invoice.pk})
        )
        self.assertEqual(response.status_code, 405)
