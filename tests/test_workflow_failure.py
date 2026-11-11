import pytest

import src.database as database
import src.workflow as workflow


def test_workflow_failure_is_audited_and_not_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "workflow.db"))
    database.initialise_database()

    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"%PDF-test-content")

    def fail_extract(_):
        raise RuntimeError("simulated PDF parser failure")

    monkeypatch.setattr(workflow, "extract_pdf_text", fail_extract)

    with pytest.raises(RuntimeError, match="simulated PDF parser failure"):
        workflow.process_invoice(str(pdf), source_filename="input.pdf")

    history = database.get_history()
    assert len(history) == 1
    run = history[0]
    assert run["processing_status"] == "PROCESSING_FAILED"
    assert run["decision"] == "NOT_DECIDED"
    assert "simulated PDF parser failure" in run["error_message"]

    steps = database.get_steps(run["run_id"])
    assert len(steps) == 1
    assert steps[0]["status"] == "FAILED"
    assert steps[0]["started_at"]
    assert steps[0]["completed_at"]
