from src.models import CheckResult
from src.rules_engine import evaluate_decision


def test_any_failure_rejects():
    decision, _, human = evaluate_decision([
        CheckResult(name="duplicate", status="FAIL", message="Duplicate found")
    ])
    assert decision == "REJECTED"
    assert human is False


def test_review_requires_human():
    decision, _, human = evaluate_decision([
        CheckResult(name="po", status="REVIEW", message="PO mismatch")
    ])
    assert decision == "PENDING_REVIEW"
    assert human is True
