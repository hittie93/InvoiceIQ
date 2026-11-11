from src.models import InvoiceData, CheckResult, WorkflowResult
from src.validation import validate_invoice
from src.vendor_verification import verify_vendor
from src.duplicate_detection import check_duplicate
from src.po_matching import match_purchase_order
from src.rules_engine import evaluate_decision
from src.evidence import build_field_evidence


def make_decision(
    run_id: str,
    invoice: InvoiceData,
    source_text: str = "",
    document_sha256: str = ""
) -> WorkflowResult:
    checks: list[CheckResult] = []
    checks.extend(validate_invoice(invoice))
    checks.append(verify_vendor(invoice.vendor_name, invoice.vendor_tax_id))
    checks.append(check_duplicate(invoice, document_sha256))
    po_check, variance = match_purchase_order(invoice)
    checks.append(po_check)

    evidence = build_field_evidence(invoice, source_text)
    unlocated_required = [
        field for field in ("invoice_number", "vendor_name", "invoice_date", "total_amount")
        if evidence.get(field, {}).get("status") == "NOT_LOCATED"
    ]
    checks.append(CheckResult(
        name="extraction_evidence",
        status="REVIEW" if unlocated_required else "PASS",
        message=(
            "Verify extracted values against the source PDF: " + ", ".join(unlocated_required)
            if unlocated_required else
            "Required extracted fields have supporting text in the document."
        ),
        details={"fields_requiring_verification": unlocated_required}
    ))

    decision, reason, human_review = evaluate_decision(checks)
    return WorkflowResult(
        run_id=run_id,
        decision=decision,
        reason=reason,
        invoice=invoice.model_dump(mode="json"),
        checks=checks,
        variance_percent=variance,
        human_review_required=human_review,
        source_text_preview=source_text[:1000],
        field_evidence=evidence,
    )
