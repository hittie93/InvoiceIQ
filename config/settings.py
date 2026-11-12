
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load local environment variables first
load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SAMPLE_INVOICES_DIR = BASE_DIR / "sample_invoices"

# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "gpt-4.1-mini")

# Cross-platform Tesseract configuration
TESSERACT_CMD = (
    os.getenv("TESSERACT_CMD")
    or shutil.which("tesseract")
    or "tesseract"
)

# Database configuration
DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    str(BASE_DIR / "invoiceiq.db")
)

PO_TOLERANCE_PERCENT = float(
    os.getenv("PO_TOLERANCE_PERCENT", "2.0")
)

VENDOR_MATCH_THRESHOLD = int(
    os.getenv("VENDOR_MATCH_THRESHOLD", "90")
)

VENDORS_PATH = DATA_DIR / "vendors.csv"
PURCHASE_ORDERS_PATH = DATA_DIR / "purchase_orders.csv"
