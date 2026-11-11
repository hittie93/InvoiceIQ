import hashlib
import time
import uuid

from src.document_processor import extract_pdf_text
from src.extraction import extract_invoice_fields
from src.decision_engine import make_decision
from src.database import (
    create_run, start_step, finish_step, complete_run, fail_run
)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_invoice(pdf_path: str, progress_callback=None, source_filename: str = ""):
    run_id = str(uuid.uuid4())
    started = time.perf_counter()
    document_hash = _sha256_file(pdf_path)
    create_run(run_id, source_filename=source_filename, document_sha256=document_hash)

    active_step = None

    def begin(step, message):
        nonlocal active_step
        active_step = (step, start_step(run_id, step, message))
        if progress_callback:
            progress_callback(step, "RUNNING", message)

    def finish(status, message, error=""):
        nonlocal active_step
        if active_step:
            step_name, step_id = active_step
            finish_step(step_id, status, message, error)
            if progress_callback:
                progress_callback(step_name, status, message)
            active_step = None

    try:
        begin("Document processing", "Reading the uploaded PDF.")
        text, used_ocr = extract_pdf_text(pdf_path)
        finish(
            "COMPLETED",
            "OCR used." if used_ocr else "Machine-readable PDF text extracted."
        )

        begin("AI extraction", "Extracting structured invoice fields with Gemini.")
        invoice = extract_invoice_fields(text)
        finish("COMPLETED", "Structured invoice fields extracted.")

        begin("Business validation", "Checking vendor, duplicates, PO and financial rules.")
        result = make_decision(run_id, invoice, text, document_hash)
        finish("COMPLETED", "All configured checks have been evaluated.")

        begin("Decision", "Applying deterministic approval and review rules.")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        complete_run(result, duration_ms=elapsed_ms)
        finish("COMPLETED", result.decision)
        return result

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        if active_step:
            finish("FAILED", error_message, error_message)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        fail_run(run_id, error_message, duration_ms=elapsed_ms)
        raise
