
from pathlib import Path
from collections import OrderedDict

import fitz
import pytesseract
import shutil

from PIL import Image, ImageOps, ImageFilter, ImageEnhance

from config.settings import TESSERACT_CMD

TESSERACT_PATH = shutil.which("tesseract")

if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


class DocumentProcessingError(Exception):
    pass


def preprocess_image(image):
    """Prepare a scanned invoice page for OCR."""

    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(1.4)
    image = image.filter(
        ImageFilter.UnsharpMask(
            radius=1.5,
            percent=180,
            threshold=3
        )
    )

    return image


def run_ocr(image, psm):
    """Run OCR and return extracted text plus average word confidence."""

    config = (
        f"--oem 3 --psm {psm} "
        "-c preserve_interword_spaces=1"
    )

    data = pytesseract.image_to_data(
        image,
        lang="eng",
        config=config,
        output_type=pytesseract.Output.DICT,
        timeout=90
    )

    lines = OrderedDict()
    confidences = []

    for i, word in enumerate(data["text"]):
        word = word.strip()

        if not word:
            continue

        try:
            confidence = float(data["conf"][i])
            if confidence >= 0:
                confidences.append(confidence)
        except (ValueError, TypeError):
            pass

        line_key = (
            data["block_num"][i],
            data["par_num"][i],
            data["line_num"][i]
        )

        lines.setdefault(line_key, []).append(word)

    text = "\n".join(
        " ".join(words) for words in lines.values()
    ).strip()

    average_confidence = (
        sum(confidences) / len(confidences)
        if confidences else 0
    )

    return text, average_confidence


def extract_page_ocr(image, page_number):
    """Try different page layouts and select the best OCR result."""

    image = preprocess_image(image)

    candidates = []

    for psm in (4, 6, 11):
        try:
            text, confidence = run_ocr(image, psm)

            if len(text) >= 20:
                candidates.append({
                    "text": text,
                    "confidence": confidence,
                    "psm": psm
                })

        except Exception:
            continue

    if not candidates:
        raise DocumentProcessingError(
            f"OCR could not read page {page_number}. "
            "Please check the scan quality."
        )

    best = max(
        candidates,
        key=lambda item: (
            item["confidence"],
            len(item["text"])
        )
    )

    return best["text"]


def extract_pdf_text(pdf_path: str) -> tuple[str, bool]:
    """
    Extract text page by page.
    Use native text for readable pages and OCR for scanned pages.
    """

    path = Path(pdf_path)

    if not path.exists():
        raise DocumentProcessingError(
            f"File not found: {path.name}"
        )

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    extracted_pages = []
    ocr_used = False

    try:
        with fitz.open(path) as doc:

            for page_number, page in enumerate(doc, start=1):

                native_text = page.get_text("text").strip()

                if len(native_text) >= 50:
                    extracted_pages.append(
                        f"\n--- PAGE {page_number} ---\n{native_text}"
                    )
                    continue

                ocr_used = True

                # Render at 400 DPI for better recognition of small text.
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(400 / 72, 400 / 72),
                    colorspace=fitz.csRGB,
                    alpha=False
                )

                image = Image.frombytes(
                    "RGB",
                    [pix.width, pix.height],
                    pix.samples
                )

                page_text = extract_page_ocr(
                    image,
                    page_number
                )

                extracted_pages.append(
                    f"\n--- PAGE {page_number} (OCR) ---\n{page_text}"
                )

        final_text = "\n".join(extracted_pages).strip()

        if len(final_text) < 20:
            raise DocumentProcessingError(
                "No readable text could be extracted from the PDF."
            )

        return final_text, ocr_used

    except DocumentProcessingError:
        raise

    except Exception as exc:
        raise DocumentProcessingError(
            "PDF processing failed. Check Tesseract installation, "
            "TESSERACT_CMD and PDF readability. "
            f"Technical detail: {type(exc).__name__}: {exc}"
        ) from exc
