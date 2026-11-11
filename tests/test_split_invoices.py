import json

import src.database as database
import src.po_matching as po_matching
from src.models import InvoiceData, InvoiceLineItem


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "split.db"))
    database.initialise_database()
    with database.get_connection() as conn:
        conn.execute("""
            INSERT INTO purchase_orders
            (po_id, vendor_id, vendor_name, po_number, po_amount, currency,
             status, line_items_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "PO-SPLIT", "V001", "ABC Technologies", "PO-SPLIT",
            "1000.00", "INR", "approved",
            json.dumps([{
                "description": "Cloud support",
                "quantity": "10",
                "unit_price": "100.00",
                "line_total": "1000.00"
            }]), database.utc_now()
        ))


def test_partial_invoice_can_consume_part_of_po(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    invoice = InvoiceData(
        vendor_name="ABC Technologies",
        po_number="PO-SPLIT",
        currency="INR",
        total_amount=400,
        line_items=[
            InvoiceLineItem(
                description="Cloud support", quantity=4,
                unit_price=100, line_total=400
            )
        ]
    )
    check, _ = po_matching.match_purchase_order(invoice)
    assert check.status == "PASS"
    assert check.details["remaining_before_invoice"] == "1000.00"
    assert len(check.details["matched_line_items"]) == 1


def test_cumulative_po_quantity_prevents_overbilling(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    with database.get_connection() as conn:
        conn.execute("""
            INSERT INTO invoice_runs
            (run_id, created_at, processing_status, result_json)
            VALUES ('previous', ?, 'COMPLETED', '{}')
        """, (database.utc_now(),))
        conn.execute("""
            INSERT INTO invoice_po_allocations
            (run_id, po_id, allocated_amount, currency, status, line_items_json, created_at)
            VALUES ('previous', 'PO-SPLIT', '800.00', 'INR', 'CONFIRMED', ?, ?)
        """, (
            json.dumps([{"po_line_index": 0, "quantity": "8"}]),
            database.utc_now()
        ))

    invoice = InvoiceData(
        vendor_name="ABC Technologies",
        po_number="PO-SPLIT",
        currency="INR",
        total_amount=300,
        line_items=[
            InvoiceLineItem(
                description="Cloud support", quantity=3,
                unit_price=100, line_total=300
            )
        ]
    )
    check, _ = po_matching.match_purchase_order(invoice)
    assert check.status == "REVIEW"
    assert any("Quantity exceeds remaining PO quantity" in msg
               for msg in [check.message])



def test_two_partial_invoices_accumulate_po_allocation(tmp_path, monkeypatch):
    from src.models import CheckResult, WorkflowResult

    _setup_db(tmp_path, monkeypatch)

    first = InvoiceData(
        invoice_number="PART-1", vendor_name="ABC Technologies",
        po_number="PO-SPLIT", total_amount=400, currency="INR",
        line_items=[InvoiceLineItem(
            description="Cloud support", quantity=4,
            unit_price=100, line_total=400
        )]
    )
    check1, variance1 = po_matching.match_purchase_order(first)
    assert check1.status == "PASS"
    database.create_run("partial-1", "part1.pdf", "hash1")
    result1 = WorkflowResult(
        run_id="partial-1", decision="APPROVED", reason="passed",
        invoice=first.model_dump(mode="json"), checks=[
            CheckResult(name="po_matching", status="PASS", message="passed",
                        details=check1.details)
        ]
    )
    database.complete_run(result1)

    second = InvoiceData(
        invoice_number="PART-2", vendor_name="ABC Technologies",
        po_number="PO-SPLIT", total_amount=600, currency="INR",
        line_items=[InvoiceLineItem(
            description="Cloud support", quantity=6,
            unit_price=100, line_total=600
        )]
    )
    check2, variance2 = po_matching.match_purchase_order(second)
    assert check2.status == "PASS"
    assert check2.details["remaining_before_invoice"] == "600.00"

    database.create_run("partial-2", "part2.pdf", "hash2")
    result2 = WorkflowResult(
        run_id="partial-2", decision="APPROVED", reason="passed",
        invoice=second.model_dump(mode="json"), checks=[
            CheckResult(name="po_matching", status="PASS", message="passed",
                        details=check2.details)
        ]
    )
    database.complete_run(result2)

    allocations = database.get_po_allocations("PO-SPLIT")
    assert len(allocations) == 2
    assert sum(float(a["allocated_amount"]) for a in allocations) == 1000.0
