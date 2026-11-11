from src.models import InvoiceData
from src.validation import validate_invoice


def test_missing_required_fields_go_to_review():
    invoice = InvoiceData(vendor_name="ABC Technologies")
    checks = validate_invoice(invoice)
    required = next(c for c in checks if c.name == "required_fields")
    assert required.status == "REVIEW"


def test_valid_amount_arithmetic_passes():
    invoice = InvoiceData(invoice_number="INV-1", vendor_name="ABC",
                          invoice_date="2026-11-01", total_amount=118,
                          subtotal=100, tax_amount=18)
    checks = validate_invoice(invoice)
    arithmetic = next(c for c in checks if c.name == "invoice_arithmetic")
    assert arithmetic.status == "PASS"
