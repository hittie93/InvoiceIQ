
from decimal import Decimal, InvalidOperation

from src.models import CheckResult, InvoiceData


REQUIRED_FIELDS = (
    "invoice_number",
    "vendor_name",
    "invoice_date",
    "total_amount",
)

TOLERANCE = Decimal("0.01")


def _decimal(value):
    if value is None or value == "":
        return None

    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def validate_invoice(invoice: InvoiceData) -> list[CheckResult]:

    checks = []

    # 1. Required field validation
    missing = [
        field
        for field in REQUIRED_FIELDS
        if getattr(invoice, field) in (None, "")
    ]

    checks.append(
        CheckResult(
            name="required_fields",
            status="REVIEW" if missing else "PASS",
            message=(
                "Missing required fields: " + ", ".join(missing)
                if missing
                else "All required invoice fields are present."
            ),
            details={"missing_fields": missing}
        )
    )

    # 2. Monetary value validation
    amount_values = {
        "subtotal": invoice.subtotal,
        "tax_amount": invoice.tax_amount,
        "total_amount": invoice.total_amount,
    }

    invalid = []

    for name, value in amount_values.items():
        number = _decimal(value)

        if value is not None and (
            number is None or number < 0
        ):
            invalid.append(name)

    checks.append(
        CheckResult(
            name="amount_sanity",
            status="FAIL" if invalid else "PASS",
            message=(
                "Invalid or negative monetary values found: "
                + ", ".join(invalid)
                if invalid
                else "No negative or invalid monetary values detected."
            ),
            details={"invalid_fields": invalid}
        )
    )

    # 3. Invoice arithmetic validation
    subtotal = _decimal(invoice.subtotal)
    tax = _decimal(invoice.tax_amount)
    total = _decimal(invoice.total_amount)

    if subtotal is None or tax is None or total is None:

        checks.append(
            CheckResult(
                name="invoice_arithmetic",
                status="NOT_CHECKED",
                message=(
                    "Arithmetic check skipped because subtotal, "
                    "tax or total is missing or invalid."
                ),
                details={
                    "subtotal_available": subtotal is not None,
                    "tax_available": tax is not None,
                    "total_available": total is not None,
                }
            )
        )

    else:
        calculated = (subtotal + tax).quantize(
            Decimal("0.01")
        )

        difference = abs(calculated - total).quantize(
            Decimal("0.01")
        )

        passed = difference <= TOLERANCE

        checks.append(
            CheckResult(
                name="invoice_arithmetic",
                status="PASS" if passed else "FAIL",
                message=(
                    "Subtotal plus tax reconciles to total."
                    if passed
                    else (
                        f"Financial mismatch: subtotal plus tax "
                        f"equals {calculated}, but invoice total "
                        f"is {total}. Difference: {difference}."
                    )
                ),
                details={
                    "subtotal": str(subtotal),
                    "tax_amount": str(tax),
                    "printed_total": str(total),
                    "calculated_total": str(calculated),
                    "difference": str(difference),
                    "rounding_tolerance": str(TOLERANCE),
                }
            )
        )

    # 4. Line item validation
    line_errors = []
    line_reviews = []

    if not invoice.line_items:
        line_reviews.append("No line items were extracted.")

    for index, line in enumerate(invoice.line_items, start=1):

        quantity = _decimal(line.quantity)
        unit_price = _decimal(line.unit_price)
        line_total = _decimal(line.line_total)

        # Invalid values are hard failures.
        if line.quantity is not None and quantity is None:
            line_errors.append(
                f"Line {index}: invalid quantity."
            )

        if line.unit_price is not None and unit_price is None:
            line_errors.append(
                f"Line {index}: invalid unit price."
            )

        if line.line_total is not None and line_total is None:
            line_errors.append(
                f"Line {index}: invalid line total."
            )

        if quantity is not None and quantity < 0:
            line_errors.append(
                f"Line {index}: negative quantity."
            )

        if unit_price is not None and unit_price < 0:
            line_errors.append(
                f"Line {index}: negative unit price."
            )

        if line_total is not None and line_total < 0:
            line_errors.append(
                f"Line {index}: negative line total."
            )

        # Missing values require human verification.
        if quantity is None:
            line_reviews.append(
                f"Line {index}: quantity is missing or unreadable."
            )

        if unit_price is None:
            line_reviews.append(
                f"Line {index}: unit price is missing or unreadable."
            )

        if line_total is None:
            line_reviews.append(
                f"Line {index}: line total is missing or unreadable."
            )

        # Compare only when all three values are available.
        if (
            quantity is not None
            and unit_price is not None
            and line_total is not None
            and quantity >= 0
            and unit_price >= 0
            and line_total >= 0
        ):
            expected = (
                quantity * unit_price
            ).quantize(Decimal("0.01"))

            if abs(expected - line_total) > TOLERANCE:
                line_errors.append(
                    f"Line {index}: quantity multiplied by unit "
                    f"price equals {expected}, but line total "
                    f"is {line_total}."
                )

    # 5. Compare sum of line totals with subtotal.
    if invoice.line_items and subtotal is not None:

        line_totals = [
            _decimal(line.line_total)
            for line in invoice.line_items
        ]

        if all(value is not None for value in line_totals):

            line_sum = sum(
                line_totals, Decimal("0")
            ).quantize(Decimal("0.01"))

            if abs(line_sum - subtotal) > TOLERANCE:
                line_errors.append(
                    f"Sum of line totals ({line_sum}) "
                    f"does not match subtotal ({subtotal})."
                )

        else:
            line_reviews.append(
                "Line total comparison skipped because one or "
                "more line totals are missing."
            )

    # FAIL takes priority over REVIEW.
    if line_errors:
        line_status = "FAIL"
        line_message = " ".join(line_errors)

    elif line_reviews:
        line_status = "REVIEW"
        line_message = " ".join(line_reviews)

    else:
        line_status = "PASS"
        line_message = (
            "Line-item quantities, prices and totals "
            "are internally consistent."
        )

    checks.append(
        CheckResult(
            name="line_item_arithmetic",
            status=line_status,
            message=line_message,
            details={
                "issues": line_errors,
                "verification_required": line_reviews,
            }
        )
    )

    return checks
