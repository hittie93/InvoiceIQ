
from src.models import InvoiceData
from src.duplicate_detection import check_duplicate


def test_duplicate_invoice_is_rejected(monkeypatch):
    invoice = InvoiceData(
        invoice_number="INV-2026-001",
        vendor_name="ABC TECHNOLOGIES",
        vendor_tax_id="27ABCDE1234F1Z5",
        total_amount=59000
    )

    monkeypatch.setattr(
        "src.duplicate_detection.find_duplicate",
        lambda *args: {
            "run_id": "previous-run-123",
            "decision": "APPROVED",
            "processing_status": "COMPLETED"
        }
    )

    result = check_duplicate(invoice, "sample-hash")

    assert result.status == "FAIL"
    assert result.details["is_confirmed_duplicate"] is True


def test_new_invoice_passes_duplicate_check(monkeypatch):
    invoice = InvoiceData(
        invoice_number="INV-2026-002",
        vendor_name="ABC TECHNOLOGIES",
        total_amount=59000
    )

    monkeypatch.setattr(
        "src.duplicate_detection.find_duplicate",
        lambda *args: None
    )

    result = check_duplicate(invoice, "new-hash")

    assert result.status == "PASS"
