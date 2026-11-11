
from src.models import InvoiceData, InvoiceLineItem
import src.database as database
import src.workflow as workflow
from config.settings import BASE_DIR


def test_real_pdf_happy_path_with_mocked_gemini(tmp_path, monkeypatch):

    # 1. Initialize an isolated test database
    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        str(tmp_path / "happy.db")
    )
    database.initialise_database()

    # 2. Create mocked Gemini extraction response
    invoice = InvoiceData(
        invoice_number="INV-2026-001",
        vendor_name="ABC TECHNOLOGIES",
        vendor_tax_id="27ABCDE1234F1Z5",
        invoice_date="2026-11-01",
        due_date="2026-11-30",
        po_number="PO-1001",
        currency="INR",
        subtotal=50000,
        tax_amount=9000,
        total_amount=59000,
        line_items=[
            InvoiceLineItem(
                description="Enterprise software services",
                quantity=1,
                unit_price=50000,
                line_total=50000
            )
        ]
    )

    monkeypatch.setattr(
        workflow,
        "extract_invoice_fields",
        lambda text: invoice
    )

    # 3. Locate the real sample PDF
    pdf_path = (
        BASE_DIR
        / "sample_invoices"
        / "sample_happy_path_invoice.pdf"
    )

    assert pdf_path.exists(), f"Sample invoice not found: {pdf_path}"

    # 4. Execute the complete invoice workflow
    result = workflow.process_invoice(
        str(pdf_path),
        source_filename=pdf_path.name
    )

    # 5. Debugging information
    print("\n========== WORKFLOW DEBUG ==========")

    print("Run ID:", result.run_id)
    print("Decision:", result.decision)
    print("Reason:", result.reason)

    print("\nValidation checks:")

    for check in result.checks:
        print("--------------------------------")
        print("Name:", check.name)
        print("Status:", check.status)
        print("Message:", check.message)
        print("Details:", check.details)

    print("\nExtracted invoice:")
    print(result.invoice)

    print("====================================\n")

    # 6. Verify business decision
    assert result.decision == "APPROVED", (
        f"Expected APPROVED, got {result.decision}. "
        f"Reason: {result.reason}"
    )

    assert result.human_review_required is False

    # 7. Verify database history
    history = database.get_history()

    assert len(history) == 1
    assert history[0]["processing_status"] == "COMPLETED"
    assert history[0]["duration_ms"] >= 0

    # 8. Verify PO allocation
    allocations = database.get_po_allocations("PO-1001")

    assert len(allocations) == 1

    # 9. Verify workflow execution stages
    steps = database.get_steps(result.run_id)

    assert [step["status"] for step in steps] == [
        "COMPLETED",
        "COMPLETED",
        "COMPLETED",
        "COMPLETED"
    ]
