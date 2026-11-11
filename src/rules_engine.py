from src.models import CheckResult


def evaluate_decision(checks: list[CheckResult]) -> tuple[str, str, bool]:
    """Apply explicit rules. FAIL is a hard stop; REVIEW requires a person."""
    failures = [c for c in checks if c.status == "FAIL"]
    reviews = [c for c in checks if c.status in ("REVIEW", "NOT_CHECKED")]

    if failures:
        reason = "; ".join(f"{c.name}: {c.message}" for c in failures)
        return "REJECTED", reason, False

    if reviews:
        reason = "; ".join(f"{c.name}: {c.message}" for c in reviews)
        return "PENDING_REVIEW", reason, True

    return "APPROVED", "All configured validation checks passed.", False
