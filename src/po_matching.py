import json
from decimal import Decimal, InvalidOperation

from rapidfuzz import fuzz

from config.settings import PO_TOLERANCE_PERCENT
from src.database import get_po, get_po_allocations
from src.models import CheckResult, InvoiceData


def money(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid monetary value: {value}")


def _line_amount(line):
    if line.line_total is not None:
        return money(line.line_total)
    if line.quantity is not None and line.unit_price is not None:
        return (Decimal(str(line.quantity)) * money(line.unit_price)).quantize(Decimal("0.01"))
    return None


def match_purchase_order(invoice: InvoiceData) -> tuple[CheckResult, float | None]:
    if not invoice.po_number:
        return CheckResult(
            name="po_matching", status="REVIEW",
            message="PO number is missing; manual matching is required."
        ), None

    if invoice.total_amount is None:
        return CheckResult(
            name="po_matching", status="REVIEW",
            message="Invoice total is missing; PO amount cannot be compared."
        ), None

    po = get_po(invoice.po_number)
    if not po:
        return CheckResult(
            name="po_matching", status="REVIEW",
            message=f"Purchase order {invoice.po_number} was not found."
        ), None

    if str(po["status"]).strip().lower() != "approved":
        return CheckResult(
            name="po_matching", status="REVIEW",
            message=f"Purchase order {invoice.po_number} is not approved.",
            details={"po_status": po["status"]}
        ), None

    if str(po["vendor_name"]).strip().casefold() != str(invoice.vendor_name or "").strip().casefold():
        return CheckResult(
            name="po_matching", status="REVIEW",
            message="PO vendor does not exactly match the extracted invoice vendor.",
            details={"po_vendor": po["vendor_name"], "invoice_vendor": invoice.vendor_name}
        ), None

    po_currency = str(po.get("currency", "INR")).upper()
    invoice_currency = str(invoice.currency or "INR").upper()
    if po_currency != invoice_currency:
        return CheckResult(
            name="po_matching", status="REVIEW",
            message="Invoice currency differs from PO currency.",
            details={"po_currency": po_currency, "invoice_currency": invoice_currency}
        ), None

    po_amount = money(po["po_amount"])
    invoice_amount = money(invoice.total_amount)
    allocations = get_po_allocations(invoice.po_number)
    allocated_amount = sum((money(a["allocated_amount"]) for a in allocations), Decimal("0"))
    remaining = max(Decimal("0"), po_amount - allocated_amount)
    tolerance = Decimal(str(PO_TOLERANCE_PERCENT)) / Decimal("100")
    allowed_remaining = remaining * (Decimal("1") + tolerance)

    overage = invoice_amount > allowed_remaining
    variance = (abs(invoice_amount - remaining) / remaining * Decimal("100")) if remaining else (
        Decimal("100") if invoice_amount > 0 else Decimal("0")
    )

    # Reconcile itemised invoices when the PO master contains line-level detail.
    try:
        po_lines = json.loads(po.get("line_items_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        po_lines = []

    matched_lines = []
    line_issues = []
    if po_lines:
        used_invoice_indexes = set()
        prior_line_qty = {}
        for allocation in allocations:
            try:
                prior_items = json.loads(allocation.get("line_items_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                prior_items = []
            for item in prior_items:
                idx = item.get("po_line_index")
                if idx is not None:
                    prior_line_qty[idx] = prior_line_qty.get(idx, Decimal("0")) + Decimal(str(item.get("quantity") or 0))

        for inv_index, inv_line in enumerate(invoice.line_items):
            description = (inv_line.description or "").strip()
            if not description:
                line_issues.append(f"Invoice line {inv_index + 1} has no description.")
                continue

            candidates = []
            for po_index, po_line in enumerate(po_lines):
                score = fuzz.token_set_ratio(description, str(po_line.get("description", "")))
                candidates.append((score, po_index, po_line))
            if not candidates:
                line_issues.append(f"No PO line available for '{description}'.")
                continue

            score, po_index, po_line = max(candidates, key=lambda x: x[0])
            if score < 80:
                line_issues.append(f"No sufficiently close PO line match for '{description}' (best score {score}%).")
                continue

            if inv_line.quantity is None or inv_line.unit_price is None:
                line_issues.append(f"Quantity or unit price missing for '{description}'.")
                continue

            invoice_qty = Decimal(str(inv_line.quantity))
            ordered_qty = Decimal(str(po_line.get("quantity", 0)))
            already_used = prior_line_qty.get(po_index, Decimal("0"))
            current_used = sum(
                (Decimal(str(x["quantity"])) for x in matched_lines if x["po_line_index"] == po_index),
                Decimal("0")
            )
            if already_used + current_used + invoice_qty > ordered_qty:
                line_issues.append(
                    f"Quantity exceeds remaining PO quantity for '{description}'. "
                    f"Remaining: {ordered_qty - already_used - current_used}."
                )
                continue

            po_unit_price = money(po_line.get("unit_price"))
            invoice_unit_price = money(inv_line.unit_price)
            price_variance = (
                abs(invoice_unit_price - po_unit_price) / po_unit_price * Decimal("100")
                if po_unit_price else Decimal("100")
            )
            if price_variance > Decimal(str(PO_TOLERANCE_PERCENT)):
                line_issues.append(
                    f"Unit price variance for '{description}' is {price_variance:.2f}%."
                )
                continue

            line_total = _line_amount(inv_line)
            matched_lines.append({
                "invoice_line_index": inv_index,
                "po_line_index": po_index,
                "description": description,
                "match_score": score,
                "quantity": str(invoice_qty),
                "unit_price": str(invoice_unit_price),
                "line_total": str(line_total) if line_total is not None else None
            })

        if len(matched_lines) != len(invoice.line_items) and not line_issues:
            line_issues.append("Not all invoice lines could be matched to PO lines.")
    elif invoice.line_items:
        line_issues.append(
            "PO line-item details are unavailable; header-level matching alone is insufficient for automatic approval."
        )
    elif not invoice.line_items:
        line_issues.append(
            "Invoice contains no extracted line items; line-item reconciliation cannot be completed."
        )

    status = "REVIEW" if overage or line_issues else "PASS"
    messages = []
    if overage:
        messages.append(
            f"Invoice amount {invoice_amount} exceeds remaining PO balance {remaining} "
            f"plus {PO_TOLERANCE_PERCENT:.2f}% tolerance."
        )
    if line_issues:
        messages.extend(line_issues)
    if not messages:
        messages.append(
            f"PO matched. Remaining balance before this invoice: {remaining}; "
            f"invoice amount: {invoice_amount}."
        )

    details = {
        "po_number": invoice.po_number,
        "po_amount": str(po_amount),
        "previously_allocated": str(allocated_amount),
        "remaining_before_invoice": str(remaining),
        "invoice_amount": str(invoice_amount),
        "variance_percent": round(float(variance), 2),
        "tolerance_percent": PO_TOLERANCE_PERCENT,
        "matched_line_items": matched_lines,
        "line_item_check": "PASS" if po_lines and not line_issues else (
            "REVIEW" if line_issues else "NOT_CONFIGURED"
        )
    }
    return CheckResult(
        name="po_matching", status=status,
        message=" ".join(messages), details=details
    ), round(float(variance), 2)
