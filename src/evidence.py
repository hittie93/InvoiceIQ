
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


def _normalise_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _number_forms(value):
    try:
        number = Decimal(str(value))
        return {
            format(number, "f"),
            format(number.quantize(Decimal("0.01")), "f"),
            str(number.normalize())
        }
    except (InvalidOperation, ValueError):
        return set()


def _parse_date(value):
    """Convert supported date formats into a standard YYYY-MM-DD string."""
    value = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%m/%d/%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def _date_found(value, source_text):
    """Check whether an extracted date appears in source text in another format."""
    expected = _parse_date(value)

    if not expected:
        return False, None

    # Find common numeric and written date representations.
    date_pattern = re.compile(
        r"\b(?:"
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
        r"|"
        r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
        r"|"
        r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"
        r"|"
        r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
        r")\b",
        re.IGNORECASE
    )

    for match in date_pattern.finditer(source_text):
        candidate = match.group(0)
        parsed = _parse_date(candidate)

        if parsed == expected:
            start = max(0, match.start() - 70)
            end = min(len(source_text), match.end() + 70)
            excerpt = source_text[start:end].replace("\n", " ")
            return True, excerpt

    return False, None


def build_field_evidence(invoice, source_text: str) -> dict:
    """Provide traceable text evidence; never invent numeric confidence percentages."""
    text_norm = _normalise_text(source_text)
    evidence = {}

    scalar_fields = (
        "invoice_number",
        "vendor_name",
        "vendor_tax_id",
        "invoice_date",
        "due_date",
        "po_number"
    )

    for field in scalar_fields:
        value = getattr(invoice, field, None)

        if value in (None, ""):
            evidence[field] = {
                "value": value,
                "status": "MISSING",
                "evidence": None,
                "note": "No value was extracted."
            }
            continue

        if field in ("invoice_date", "due_date"):
            found, excerpt = _date_found(value, source_text)
        else:
            needle = _normalise_text(value)
            found = bool(needle and needle in text_norm)
            excerpt = None

            if found:
                raw = str(value)
                pos = source_text.casefold().find(raw.casefold())

                if pos >= 0:
                    start = max(0, pos - 70)
                    end = min(len(source_text), pos + len(raw) + 70)
                    excerpt = source_text[start:end].replace("\n", " ")

        evidence[field] = {
            "value": value,
            "status": "FOUND_IN_SOURCE" if found else "NOT_LOCATED",
            "evidence": excerpt,
            "note": (
                "Value located in extracted document text."
                if found else
                "Value was extracted but supporting text was not located; verify against the PDF."
            )
        }

    for field in ("subtotal", "tax_amount", "total_amount"):
        value = getattr(invoice, field, None)

        if value is None:
            evidence[field] = {
                "value": None,
                "status": "MISSING",
                "evidence": None,
                "note": "No value was extracted."
            }
            continue

        canonical = None

        try:
            canonical = Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            pass

        candidates = set(
            re.findall(r"\d[\d,]*(?:\.\d{1,2})?", source_text)
        )

        found = False

        for candidate in candidates:
            try:
                number = Decimal(
                    candidate.replace(",", "")
                ).quantize(Decimal("0.01"))

                if canonical is not None and number == canonical:
                    found = True
                    break

            except InvalidOperation:
                continue

        evidence[field] = {
            "value": value,
            "status": "FOUND_IN_SOURCE" if found else "NOT_LOCATED",
            "evidence": None,
            "note": (
                "Numeric value appears in extracted document text."
                if found else
                "Numeric value was not confidently located in extracted text; verify against the PDF."
            )
        }

    evidence["line_items"] = {
        "value": len(invoice.line_items),
        "status": "EXTRACTED" if invoice.line_items else "EMPTY",
        "evidence": None,
        "note": f"{len(invoice.line_items)} line item(s) extracted."
    }

    return evidence
