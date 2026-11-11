
from src.database import find_duplicate
from src.models import InvoiceData, CheckResult


def check_duplicate(
    invoice: InvoiceData,
    document_sha256: str = ""
) -> CheckResult:

    if not invoice.invoice_number or not invoice.vendor_name:
        return CheckResult(
            name="duplicate_detection",
            status="NOT_CHECKED",
            message=(
                "Duplicate check skipped because vendor or "
                "invoice number is missing."
            )
        )

    existing = find_duplicate(
        invoice.vendor_name,
        invoice.invoice_number,
        document_sha256
    )

    if existing:
        return CheckResult(
            name="duplicate_detection",
            status="FAIL",
            message=(
                "Confirmed duplicate invoice. A matching previously "
                f"processed invoice was found: {existing['run_id']}."
            ),
            details={
                "previous_run_id": existing["run_id"],
                "previous_decision": existing.get("decision"),
                "duplicate_basis": (
                    "DOCUMENT_HASH_OR_VENDOR_INVOICE_NUMBER"
                ),
                "is_confirmed_duplicate": True
            }
        )

    return CheckResult(
        name="duplicate_detection",
        status="PASS",
        message=(
            "No matching vendor/invoice number or "
            "document fingerprint found."
        )
    )
