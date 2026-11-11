import sqlite3

import src.database as database


def test_initialise_database_migrates_legacy_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE invoice_runs (
            run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
            invoice_number TEXT, vendor_name TEXT, total_amount REAL,
            decision TEXT NOT NULL, reason TEXT, result_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE workflow_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            step_name TEXT NOT NULL, status TEXT NOT NULL,
            message TEXT, created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.initialise_database()

    with database.get_connection() as migrated:
        run_columns = {r["name"] for r in migrated.execute("PRAGMA table_info(invoice_runs)")}
        step_columns = {r["name"] for r in migrated.execute("PRAGMA table_info(workflow_steps)")}
        tables = {r["name"] for r in migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}

    assert "processing_status" in run_columns
    assert "duration_ms" in run_columns
    assert "started_at" in step_columns
    assert "completed_at" in step_columns
    assert "purchase_orders" in tables
    assert "invoice_po_allocations" in tables


def test_failed_run_is_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "runs.db"))
    database.initialise_database()
    database.create_run("run-failed", "broken.pdf", "abc123")
    database.fail_run("run-failed", "Gemini unavailable", 123)

    history = database.get_history()
    row = next(r for r in history if r["run_id"] == "run-failed")
    assert row["processing_status"] == "PROCESSING_FAILED"
    assert row["decision"] == "NOT_DECIDED"
    assert row["error_message"] == "Gemini unavailable"
    assert row["duration_ms"] == 123
