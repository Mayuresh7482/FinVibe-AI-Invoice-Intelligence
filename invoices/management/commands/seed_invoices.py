"""
FinVibe — Management command to seed sample invoices for demo/testing.
"""
import random
from decimal import Decimal
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandParser

from invoices.models import Invoice, CategoryChoices


SAMPLE_INVOICES = [
    {
        "vendor_name": "Tata Consultancy Services",
        "raw_text": "Invoice No: TCS-2025-4421\nDate: 15/01/2025\nFrom: Tata Consultancy Services Ltd.\nBill To: FinVibe Pvt Ltd\nDescription: Software Development Services - January 2025\nSubtotal: ₹2,50,000.00\nGST (18%): ₹45,000.00\nTotal Amount Due: ₹2,95,000.00\nPayment Terms: Net 30\nBank: HDFC Bank, Account: 50200012345678",
        "amount": Decimal("295000.00"),
        "category": "Professional Services",
        "date": date(2025, 1, 15),
    },
    {
        "vendor_name": "Amazon Web Services",
        "raw_text": "AWS Invoice\nInvoice #: AWS-INV-7891234\nDate: 2025-02-01\nBill To: FinVibe Pvt Ltd\nService Charges:\n  EC2 Instances: $450.00\n  S3 Storage: $120.00\n  RDS Database: $200.00\n  CloudFront CDN: $80.00\nSubtotal: $850.00\nTax: $0.00\nTotal: $850.00\nCurrency: USD",
        "amount": Decimal("850.00"),
        "category": "Software & SaaS",
        "date": date(2025, 2, 1),
        "currency": "USD",
    },
    {
        "vendor_name": "Swiggy Corporate",
        "raw_text": "Swiggy Corporate Invoice\nInvoice: SWG-CORP-20250115\nDate: January 15, 2025\nVendor: Swiggy Corporate Meals\nBill To: FinVibe Technologies\nTeam Lunch - 45 meals x ₹250\nAmount: ₹11,250.00\nGST @5%: ₹562.50\nTotal: ₹11,812.50\nPaid via: Corporate Card ending 4532",
        "amount": Decimal("11812.50"),
        "category": "Food & Beverage",
        "date": date(2025, 1, 15),
    },
    {
        "vendor_name": "Jio Fiber",
        "raw_text": "Reliance Jio Infocomm Limited\nBill No: JIO-FIB-202502-98765\nBill Date: 01-Feb-2025\nBill Period: Feb 2025\nPlan: Business Fiber 500 Mbps\nMonthly Charges: ₹2,499.00\nGST (18%): ₹449.82\nTotal Amount: ₹2,948.82\nDue Date: 15-Feb-2025\nCustomer ID: JIO123456789",
        "amount": Decimal("2948.82"),
        "category": "Telecom",
        "date": date(2025, 2, 1),
    },
    {
        "vendor_name": "MakeMyTrip",
        "raw_text": "MakeMyTrip - Booking Confirmation & Invoice\nBooking ID: MMT-FL-9876543\nInvoice Date: 10 Jan 2025\nPassenger: Mayuresh Borate\nFlight: Mumbai (BOM) → Bangalore (BLR)\nAirline: IndiGo 6E-2145\nDate of Travel: 25 Jan 2025\nBase Fare: ₹4,500.00\nFuel Surcharge: ₹800.00\nTaxes & Fees: ₹650.00\nConvenience Fee: ₹249.00\nTotal Amount: ₹6,199.00\nPayment: Credit Card ending 7890",
        "amount": Decimal("6199.00"),
        "category": "Travel",
        "date": date(2025, 1, 10),
    },
    {
        "vendor_name": "WeWork India",
        "raw_text": "WeWork India Management Pvt Ltd\nInvoice: WW-PUN-2025-0234\nDate: 01/01/2025\nBill To: FinVibe Technologies Pvt Ltd\nDescription: Dedicated Desk - Pune Viman Nagar\nPeriod: January 2025\nRent: ₹25,000.00\nMeeting Room Credits: ₹3,000.00\nGST (18%): ₹5,040.00\nTotal: ₹33,040.00\nPayment Due: 10/01/2025",
        "amount": Decimal("33040.00"),
        "category": "Rent",
        "date": date(2025, 1, 1),
    },
    {
        "vendor_name": "Google Workspace",
        "raw_text": "Google Cloud Invoice\nInvoice Number: GCP-INV-2025-5678\nBilling Period: Jan 1 - Jan 31, 2025\nAccount: FinVibe Tech\nGoogle Workspace Business Standard\n15 users x ₹672/user/month\nSubtotal: ₹10,080.00\nGST (18%): ₹1,814.40\nTotal: ₹11,894.40",
        "amount": Decimal("11894.40"),
        "category": "Software & SaaS",
        "date": date(2025, 1, 31),
    },
    {
        "vendor_name": "MSEB (Maharashtra Electricity)",
        "raw_text": "Maharashtra State Electricity Board\nConsumer No: 170987654321\nBill Date: 05/02/2025\nBilling Period: Jan 2025\nUnit Consumed: 850 kWh\nEnergy Charges: ₹6,800.00\nFixed Charges: ₹500.00\nElectricity Duty: ₹340.00\nTotal Amount Due: ₹7,640.00\nDue Date: 20/02/2025\nPremises: Office, Pune",
        "amount": Decimal("7640.00"),
        "category": "Utilities",
        "date": date(2025, 2, 5),
    },
    {
        "vendor_name": "Staples India",
        "raw_text": "Staples India Pvt Ltd\nInvoice: STL-202501-8765\nDate: 20-Jan-2025\nShip To: FinVibe Office, Pune\nItems:\n1. A4 Paper (10 reams) - ₹3,500.00\n2. Ink Cartridges (4 pack) - ₹2,800.00\n3. Desk Organizers (5) - ₹1,750.00\n4. Whiteboard Markers (20) - ₹600.00\nSubtotal: ₹8,650.00\nGST (18%): ₹1,557.00\nTotal: ₹10,207.00",
        "amount": Decimal("10207.00"),
        "category": "Supplies",
        "date": date(2025, 1, 20),
    },
    {
        "vendor_name": "ICICI Lombard",
        "raw_text": "ICICI Lombard General Insurance Co. Ltd.\nPolicy Invoice\nInvoice No: IL-GRP-2025-11234\nDate: 01-Jan-2025\nPolicyholder: FinVibe Technologies Pvt Ltd\nPolicy Type: Group Health Insurance\nCoverage: 20 employees\nSum Insured: ₹5,00,000 per employee\nAnnual Premium: ₹1,80,000.00\nGST (18%): ₹32,400.00\nTotal Premium: ₹2,12,400.00\nPolicy Period: 01-Jan-2025 to 31-Dec-2025",
        "amount": Decimal("212400.00"),
        "category": "Insurance",
        "date": date(2025, 1, 1),
    },
]


class Command(BaseCommand):
    help = "Seed the database with sample invoices for demo/testing."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Number of invoices to seed (default: 10, uses sample data cyclically).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing invoices before seeding.",
        )

    def handle(self, *args, **options) -> None:
        count: int = options["count"]
        clear: bool = options["clear"]

        if clear:
            deleted, _ = Invoice.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing records."))

        created = 0
        for i in range(count):
            sample = SAMPLE_INVOICES[i % len(SAMPLE_INVOICES)]
            # Add slight date variation for duplicates
            date_offset = timedelta(days=i // len(SAMPLE_INVOICES) * 30)
            inv_date = sample["date"] + date_offset

            invoice = Invoice(
                vendor_name=sample["vendor_name"],
                raw_text=sample["raw_text"],
                amount=sample["amount"],
                category=sample["category"],
                date=inv_date,
                currency=sample.get("currency", "INR"),
                parsed_by_ai=random.choice([True, False]),
                ai_confidence=round(random.uniform(0.55, 0.98), 2) if random.random() > 0.2 else None,
            )
            invoice.save()
            created += 1

        self.stdout.write(
            self.style.SUCCESS(f"✅ Seeded {created} sample invoices successfully.")
        )
