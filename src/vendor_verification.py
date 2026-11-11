import re

import pandas as pd
from rapidfuzz import process, fuzz

from config.settings import VENDORS_PATH, VENDOR_MATCH_THRESHOLD
from src.models import CheckResult

GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
)


def is_valid_gstin(value: str | None) -> bool:
    if not value:
        return False

    gstin = re.sub(r"\s+", "", str(value)).upper()

    return bool(GSTIN_PATTERN.fullmatch(gstin))


def normalize(value):
    """Normalise company names and tax identifiers for comparison."""
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())

    GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
)


def is_valid_gstin(value: str | None) -> bool:
    if not value:
        return False

    gstin = re.sub(r"\s+", "", str(value)).upper()
    return bool(GSTIN_PATTERN.fullmatch(gstin))


def verify_vendor(vendor_name: str | None, tax_id: str | None = None):
    if not VENDORS_PATH.exists():
        return CheckResult(
            name="vendor_verification",
            status="REVIEW",
            message="Vendor master file is unavailable."
        )

    vendors = pd.read_csv(VENDORS_PATH, dtype=str).fillna("")
    required_columns = {"vendor_id", "vendor_name", "status", "tax_id"}
    if not required_columns.issubset(vendors.columns):
        return CheckResult(
            name="vendor_verification",
            status="REVIEW",
            message="Vendor master is missing required columns.",
            details={"missing_columns": sorted(required_columns - set(vendors.columns))}
        )

    if vendors.empty:
        return CheckResult(
            name="vendor_verification",
            status="REVIEW",
            message="Vendor master contains no records."
        )

    vendors["normalized_name"] = vendors["vendor_name"].apply(normalize)
    vendors["normalized_tax_id"] = vendors["tax_id"].apply(normalize)
    input_name = normalize(vendor_name)
    input_tax_id = normalize(tax_id)

    if input_tax_id and not is_valid_gstin(input_tax_id):
        return CheckResult(
            name="vendor_verification",
            status="REVIEW",
            message="Extracted GSTIN has an invalid format. Verify it against the source invoice.",
            details={
                "extracted_tax_id": tax_id,
            "reason": "INVALID_GSTIN_FORMAT"
        }
    )

    row = None
    match_method = None
    match_score = None

    # A unique exact tax-ID match identifies the master record, but a name
    # discrepancy remains a review item rather than being silently approved.
    if input_tax_id:
        tax_matches = vendors[vendors["normalized_tax_id"] == input_tax_id]
        if len(tax_matches) > 1:
            return CheckResult(
                name="vendor_verification",
                status="REVIEW",
                message="Multiple vendors have the same tax ID."
            )
        if len(tax_matches) == 1:
            row = tax_matches.iloc[0]
            match_method = "EXACT_TAX_ID"
            match_score = 100

            if not input_name:
                return CheckResult(
                    name="vendor_verification",
                    status="REVIEW",
                    message="Tax ID matched, but vendor name is missing.",
                    details={
                        "vendor_id": row["vendor_id"],
                        "master_name": row["vendor_name"],
                        "match_method": match_method
                    }
                )

            if row["normalized_name"] != input_name:
                return CheckResult(
                    name="vendor_verification",
                    status="REVIEW",
                    message=(
                        "Tax ID matched, but extracted vendor name differs from "
                        "the vendor master. Confirm the issuer name; it may be a "
                        "tagline or business description."
                    ),
                    details={
                        "vendor_id": row["vendor_id"],
                        "master_name": row["vendor_name"],
                        "submitted_name": vendor_name,
                        "match_method": match_method,
                        "tax_id_verified": True
                    }
                )

    if row is None:
        if not input_name:
            return CheckResult(
                name="vendor_verification",
                status="REVIEW",
                message="Vendor name and a usable tax ID are missing."
            )

        exact_matches = vendors[vendors["normalized_name"] == input_name]
        if len(exact_matches) > 1:
            return CheckResult(
                name="vendor_verification",
                status="REVIEW",
                message="Multiple vendors have the same normalised name."
            )
        if len(exact_matches) == 1:
            row = exact_matches.iloc[0]
            match_method = "EXACT_NAME"
            match_score = 100

        else:
            names = vendors["normalized_name"].tolist()
            match = process.extractOne(input_name, names, scorer=fuzz.ratio)
            if not match:
                return CheckResult(
                    name="vendor_verification",
                    status="REVIEW",
                    message="No vendor records found."
                )

            _, score, index = match
            candidate = vendors.iloc[index]
            if score < VENDOR_MATCH_THRESHOLD:
                return CheckResult(
                    name="vendor_verification",
                    status="REVIEW",
                    message=(
                        f"No sufficiently close vendor match found. Best match: "
                        f"{candidate['vendor_name']} ({score:.2f}%)."
                    ),
                    details={
                        "candidate": candidate["vendor_name"],
                        "match_score": score,
                        "match_method": "FUZZY"
                    }
                )

            return CheckResult(
                name="vendor_verification",
                status="REVIEW",
                message="Possible vendor match found. Human verification required.",
                details={
                    "vendor_id": candidate["vendor_id"],
                    "candidate": candidate["vendor_name"],
                    "match_score": score,
                    "match_method": "FUZZY_NAME"
                }
            )

    if str(row["status"]).strip().lower() != "active":
        return CheckResult(
            name="vendor_verification",
            status="FAIL",
            message=f"Vendor {row['vendor_name']} is inactive.",
            details={
                "vendor_id": row["vendor_id"],
                "vendor_status": row["status"],
                "match_method": match_method
            }
        )

    master_tax_id = normalize(row["tax_id"])
    if input_tax_id and master_tax_id != input_tax_id:
        return CheckResult(
            name="vendor_verification",
            status="REVIEW",
            message="Vendor tax ID mismatch.",
            details={"vendor_id": row["vendor_id"]}
        )

    return CheckResult(
        name="vendor_verification",
        status="PASS",
        message=f"Vendor successfully verified: {row['vendor_name']}.",
        details={
            "vendor_id": row["vendor_id"],
            "matched_name": row["vendor_name"],
            "match_score": match_score,
            "match_method": match_method,
            "tax_id_verified": bool(input_tax_id)
        }
    )
