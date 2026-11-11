from src.models import InvoiceData
from src.po_matching import match_purchase_order


def test_missing_po_is_review():
    invoice = InvoiceData(vendor_name="ABC", total_amount=100)
    check, variance = match_purchase_order(invoice)
    assert check.status == "REVIEW"
    assert variance is None
