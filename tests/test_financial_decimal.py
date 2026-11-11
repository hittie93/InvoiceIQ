from decimal import Decimal
from src.models import InvoiceData, InvoiceLineItem
from src.validation import validate_invoice


def test_financial_arithmetic_uses_decimal_precision():
    invoice = InvoiceData(
        invoice_number="INV-1", vendor_name="ABC",
        invoice_date="2026-11-01",
        subtotal=0.1, tax_amount=0.2, total_amount=0.3
    )
    checks = validate_invoice(invoice)
    arithmetic = next(c for c in checks if c.name == "invoice_arithmetic")
    assert arithmetic.status == "PASS"
    assert Decimal(arithmetic.details["calculated_total"]) == Decimal("0.30")


def test_line_item_arithmetic_mismatch_is_flagged():
    invoice = InvoiceData(
        line_items=[
            InvoiceLineItem(
                description="Consulting", quantity=2,
                unit_price=100, line_total=250
            )
        ]
    )
    checks = validate_invoice(invoice)
    line_check = next(c for c in checks if c.name == "line_item_arithmetic")
    assert line_check.status == "REVIEW"
