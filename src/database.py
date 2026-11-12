import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

from config.settings import DATABASE_PATH, PURCHASE_ORDERS_PATH, VENDORS_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn, table, definition):
    name = definition.split()[0]
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")



def _seed_purchase_orders(conn):
    if not Path(PURCHASE_ORDERS_PATH).exists():
        return

    vendors = {}

    if Path(VENDORS_PATH).exists():
        vdf = pd.read_csv(VENDORS_PATH, dtype=str).fillna("")
        vendors = {
            str(row["vendor_name"]).strip().casefold(): row.get("vendor_id", "")
            for _, row in vdf.iterrows()
        }

    df = pd.read_csv(PURCHASE_ORDERS_PATH, dtype=str).fillna("")

    for _, row in df.iterrows():
        po_number = str(row.get("po_number", "")).strip()

        if not po_number:
            continue

        vendor_name = str(row.get("vendor_name", "")).strip()

        # Read existing JSON line items if provided.
        line_items_raw = str(row.get("line_items_json", "")).strip()

        if line_items_raw:
            try:
                line_items = json.loads(line_items_raw)
                if not isinstance(line_items, list):
                    line_items = []
            except (TypeError, json.JSONDecodeError):
                line_items = []
        else:
            # Convert flat CSV columns into the JSON structure
            # expected by the PO matching engine.
            description = str(
                row.get("line_item_description", "")
            ).strip()

            quantity = str(row.get("quantity", "")).strip()
            unit_price = str(row.get("unit_price", "")).strip()

            if description and quantity and unit_price:
                line_items = [
                    {
                        "description": description,
                        "quantity": quantity,
                        "unit_price": unit_price
                    }
                ]
            else:
                line_items = []

        line_items_json = json.dumps(line_items)

        conn.execute("""
            INSERT INTO purchase_orders
            (
                po_id,
                vendor_id,
                vendor_name,
                po_number,
                po_amount,
                currency,
                status,
                line_items_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(po_number) DO UPDATE SET
                vendor_id=excluded.vendor_id,
                vendor_name=excluded.vendor_name,
                po_amount=excluded.po_amount,
                currency=excluded.currency,
                status=excluded.status,
                line_items_json=excluded.line_items_json,
                updated_at=excluded.updated_at
        """, (
            po_number,
            vendors.get(vendor_name.casefold()),
            vendor_name,
            po_number,
            str(row.get("po_amount", "0")),
            str(row.get("currency", "INR")).upper(),
            str(row.get("status", "approved")).lower(),
            line_items_json,
            utc_now()
        ))


def initialise_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                invoice_number TEXT,
                vendor_name TEXT,
                total_amount TEXT,
                decision TEXT,
                reason TEXT,
                result_json TEXT NOT NULL DEFAULT '{}',
                processing_status TEXT NOT NULL DEFAULT 'COMPLETED',
                vendor_id TEXT,
                source_filename TEXT,
                document_sha256 TEXT,
                duration_ms INTEGER,
                exception_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                vendor_key TEXT,
                invoice_number_key TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                FOREIGN KEY(run_id) REFERENCES invoice_runs(run_id)
            )
        """)
        # Safe, additive migration for databases created by earlier InvoiceIQ versions.
        for definition in (
            "processing_status TEXT NOT NULL DEFAULT 'COMPLETED'",
            "vendor_id TEXT",
            "source_filename TEXT",
            "document_sha256 TEXT",
            "duration_ms INTEGER",
            "exception_count INTEGER NOT NULL DEFAULT 0",
            "error_message TEXT",
            "vendor_key TEXT",
            "invoice_number_key TEXT",
        ):
            _add_column(conn, "invoice_runs", definition)
        for definition in (
            "started_at TEXT", "completed_at TEXT", "error_message TEXT"
        ):
            _add_column(conn, "workflow_steps", definition)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                po_id TEXT PRIMARY KEY,
                vendor_id TEXT,
                vendor_name TEXT NOT NULL,
                po_number TEXT NOT NULL UNIQUE,
                po_amount TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'INR',
                status TEXT NOT NULL DEFAULT 'approved',
                line_items_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_po_allocations (
                allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                po_id TEXT NOT NULL,
                allocated_amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'CONFIRMED',
                line_items_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES invoice_runs(run_id),
                FOREIGN KEY(po_id) REFERENCES purchase_orders(po_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_vendor_invoice ON invoice_runs(vendor_key, invoice_number_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON invoice_runs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_steps_run ON workflow_steps(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_allocations_po ON invoice_po_allocations(po_id, status)")
        _seed_purchase_orders(conn)



def reset_invoice_history():
    """
    Clear invoice processing history and PO allocations.
    Preserve purchase orders and vendor master CSV data.
    """
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")

        conn.execute("DELETE FROM invoice_po_allocations")
        conn.execute("DELETE FROM workflow_steps")
        conn.execute("DELETE FROM invoice_runs")

        conn.commit()

    return True


def create_run(run_id: str, source_filename: str = "", document_sha256: str = ""):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO invoice_runs
            (run_id, created_at, processing_status, decision, result_json, source_filename, document_sha256)
            VALUES (?, ?, 'PROCESSING', 'NOT_DECIDED', '{}', ?, ?)
        """, (run_id, utc_now(), source_filename, document_sha256))


def start_step(run_id: str, step_name: str, message: str = "") -> int:
    now = utc_now()
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO workflow_steps
            (run_id, step_name, status, message, created_at, started_at)
            VALUES (?, ?, 'RUNNING', ?, ?, ?)
        """, (run_id, step_name, message, now, now))
        return cur.lastrowid


def finish_step(step_id: int, status: str, message: str = "", error_message: str = ""):
    with get_connection() as conn:
        conn.execute("""
            UPDATE workflow_steps
            SET status=?, message=?, completed_at=?, error_message=?
            WHERE id=?
        """, (status, message, utc_now(), error_message or None, step_id))


def add_step(run_id: str, step_name: str, status: str, message: str = ""):
    """Backward-compatible helper for callers that create one-off audit events."""
    now = utc_now()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO workflow_steps
            (run_id, step_name, status, message, created_at,
             started_at, completed_at, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, step_name, status, message, now,
              now if status == "RUNNING" else None,
              now if status != "RUNNING" else None,
              message if status == "FAILED" else None))



def complete_run(result, duration_ms: int = 0, exception_count: int = 0):
    invoice = result.invoice
    vendor_name = invoice.get("vendor_name") or ""
    invoice_number = invoice.get("invoice_number") or ""
    vendor_key = "".join(ch.lower() for ch in vendor_name if ch.isalnum())
    invoice_key = "".join(ch.lower() for ch in invoice_number if ch.isalnum())
    vendor_id = next((c.details.get("vendor_id") for c in result.checks
                      if c.details.get("vendor_id")), None)
    po_check = next((c for c in result.checks if c.name == "po_matching"), None)
    po_number = po_check.details.get("po_number") if po_check else None
    allocation_po = None

    with get_connection() as conn:
        # Serialise the final allocation decision so concurrent runs cannot
        # both consume the same remaining PO balance.
        conn.execute("BEGIN IMMEDIATE")

        if result.decision == "APPROVED" and po_number:
            po = conn.execute(
                "SELECT po_id, po_amount, currency FROM purchase_orders WHERE po_number=?",
                (po_number,)
            ).fetchone()
            if po:
                allocated_rows = conn.execute("""
                    SELECT allocated_amount FROM invoice_po_allocations
                    WHERE po_id=? AND status='CONFIRMED'
                """, (po["po_id"],)).fetchall()
                from decimal import Decimal
                from config.settings import PO_TOLERANCE_PERCENT

                already_allocated = sum(
                    (Decimal(str(row["allocated_amount"])) for row in allocated_rows),
                    Decimal("0")
                )
                remaining = max(
                    Decimal("0"),
                    Decimal(str(po["po_amount"])) - already_allocated
                )
                amount = Decimal(str(invoice.get("total_amount") or 0))
                max_allowed = remaining * (
                    Decimal("1") + Decimal(str(PO_TOLERANCE_PERCENT)) / Decimal("100")
                )
                allocation_issue = None
                if amount > max_allowed:
                    allocation_issue = (
                        "PO allocation changed during processing. "
                        f"Remaining PO balance is {remaining}; invoice amount is {amount}."
                    )

                # Recheck cumulative PO line quantities inside the same write transaction.
                if allocation_issue is None and po_check:
                    po_master = conn.execute(
                        "SELECT line_items_json FROM purchase_orders WHERE po_id=?",
                        (po["po_id"],)
                    ).fetchone()
                    try:
                        master_lines = json.loads(po_master["line_items_json"] or "[]")
                    except (TypeError, json.JSONDecodeError):
                        master_lines = []
                    previous_rows = conn.execute("""
                        SELECT line_items_json FROM invoice_po_allocations
                        WHERE po_id=? AND status='CONFIRMED'
                    """, (po["po_id"],)).fetchall()
                    used_qty = {}
                    for previous in previous_rows:
                        try:
                            previous_items = json.loads(previous["line_items_json"] or "[]")
                        except (TypeError, json.JSONDecodeError):
                            previous_items = []
                        for item in previous_items:
                            idx = item.get("po_line_index")
                            if idx is not None:
                                used_qty[idx] = used_qty.get(idx, Decimal("0")) + Decimal(
                                    str(item.get("quantity") or "0")
                                )
                    for item in po_check.details.get("matched_line_items", []):
                        idx = item.get("po_line_index")
                        if idx is None or idx >= len(master_lines):
                            continue
                        new_qty = Decimal(str(item.get("quantity") or "0"))
                        ordered_qty = Decimal(str(master_lines[idx].get("quantity") or "0"))
                        if used_qty.get(idx, Decimal("0")) + new_qty > ordered_qty:
                            allocation_issue = (
                                "PO line quantity was consumed by another invoice during processing. "
                                f"Line: {master_lines[idx].get('description', idx)}."
                            )
                            break

                if allocation_issue:
                    result.decision = "PENDING_REVIEW"
                    result.human_review_required = True
                    result.reason = allocation_issue + " Human review is required."
                    if po_check:
                        po_check.status = "REVIEW"
                        po_check.message = result.reason
                else:
                    allocation_po = po

        conn.execute("""
            UPDATE invoice_runs SET
                invoice_number=?, vendor_name=?, total_amount=?, decision=?, reason=?,
                result_json=?, processing_status='COMPLETED', vendor_id=?,
                duration_ms=?, exception_count=?, error_message=NULL,
                vendor_key=?, invoice_number_key=?
            WHERE run_id=?
        """, (
            invoice_number or None, vendor_name or None,
            str(invoice.get("total_amount")) if invoice.get("total_amount") is not None else None,
            result.decision, result.reason, result.model_dump_json(),
            vendor_id, int(duration_ms), int(exception_count),
            vendor_key, invoice_key, result.run_id
        ))

        if allocation_po and result.decision == "APPROVED":
            conn.execute("""
                INSERT OR IGNORE INTO invoice_po_allocations
                (run_id, po_id, allocated_amount, currency, status, line_items_json, created_at)
                VALUES (?, ?, ?, ?, 'CONFIRMED', ?, ?)
            """, (
                result.run_id, allocation_po["po_id"],
                str(invoice.get("total_amount") or "0"),
                allocation_po["currency"],
                json.dumps(po_check.details.get("matched_line_items", []) if po_check else []),
                utc_now()
            ))


def fail_run(run_id: str, error_message: str, duration_ms: int = 0):
    with get_connection() as conn:
        conn.execute("""
            UPDATE invoice_runs
            SET processing_status='PROCESSING_FAILED',
                decision='NOT_DECIDED', reason=?, error_message=?,
                duration_ms=?, exception_count=1
            WHERE run_id=?
        """, (error_message, error_message, int(duration_ms), run_id))


def save_run(result):
    """Compatibility wrapper for older callers."""
    complete_run(result)


def find_duplicate(vendor_name: str, invoice_number: str, document_sha256: str = ""):
    vendor_key = "".join(ch.lower() for ch in (vendor_name or "") if ch.isalnum())
    invoice_key = "".join(ch.lower() for ch in (invoice_number or "") if ch.isalnum())
    with get_connection() as conn:
        row = None
        if vendor_key and invoice_key:
            row = conn.execute("""
                SELECT run_id, decision, processing_status
                FROM invoice_runs
                WHERE vendor_key=? AND invoice_number_key=?
                  AND processing_status='COMPLETED'
                ORDER BY created_at LIMIT 1
            """, (vendor_key, invoice_key)).fetchone()
        if row is None and vendor_name and invoice_number:
            # Compatibility with legacy rows created before normalised keys were added.
            row = conn.execute("""
                SELECT run_id, decision, processing_status
                FROM invoice_runs
                WHERE lower(trim(vendor_name))=lower(trim(?))
                  AND lower(trim(invoice_number))=lower(trim(?))
                  AND processing_status='COMPLETED'
                ORDER BY created_at LIMIT 1
            """, (vendor_name, invoice_number)).fetchone()
        if row is None and document_sha256:
            row = conn.execute("""
                SELECT run_id, decision, processing_status
                FROM invoice_runs
                WHERE document_sha256=? AND processing_status='COMPLETED'
                ORDER BY created_at LIMIT 1
            """, (document_sha256,)).fetchone()
    return dict(row) if row else None


def get_po(po_number: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM purchase_orders WHERE po_number=?",
            (str(po_number).strip(),)
        ).fetchone()
    return dict(row) if row else None


def get_po_allocations(po_number: str):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT a.* FROM invoice_po_allocations a
            JOIN purchase_orders p ON p.po_id=a.po_id
            WHERE p.po_number=? AND a.status='CONFIRMED'
            ORDER BY a.created_at
        """, (str(po_number).strip(),)).fetchall()
    return [dict(row) for row in rows]


def get_history(limit: int = 100):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM invoice_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_steps(run_id: str):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM workflow_steps WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()
    return [dict(row) for row in rows]
