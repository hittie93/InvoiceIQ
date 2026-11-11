# InvoiceIQ

InvoiceIQ is an invoice-processing application that helps extract
information from PDF invoices, check the extracted details, and show a
clear processing result.

## Workflow architecture

``` mermaid
flowchart TD
    A[Upload invoice PDF] --> B[Read PDF content]
    B --> C{Scanned PDF?}
    C -->|Yes| D[Extract text using OCR]
    C -->|No| E[Extract PDF text]
    D --> F[AI extracts invoice details]
    E --> F
    F --> G[Validate invoice information]
    G --> H[Generate processing result]
    H --> I[Display result and save history]
```

### How it works

1.  Upload an invoice in PDF format.
2.  The application reads the PDF. For scanned documents, it uses OCR to
    read the text.
3.  Gemini extracts the invoice details into a structured format.
4.  The application checks the extracted information and invoice values.
5.  A processing result is generated and displayed in the dashboard.
6.  The run details are saved so previous processing history can be
    viewed.

## How invoices are evaluated

InvoiceIQ uses AI to extract invoice information and application logic
to evaluate it.

  -----------------------------------------------------------------------
  Check                               What it looks for
  ----------------------------------- -----------------------------------
  Required fields                     Checks whether important invoice
                                      details are present

  Amount validation                   Checks that monetary values are
                                      valid and non-negative

  Invoice arithmetic                  Checks whether subtotal plus tax
                                      matches the total

  Line-item arithmetic                Checks quantity, unit price and
                                      line total calculations

  Vendor verification                 Checks the supplier details against
                                      the vendor records

  Duplicate detection                 Checks whether the invoice may have
                                      already been processed

  PO matching                         Compares the invoice with the
                                      related purchase order

  Extraction evidence                 Checks whether important extracted
                                      values are supported by the
                                      document
  -----------------------------------------------------------------------

### Processing outcomes

  -----------------------------------------------------------------------
  Result                              Meaning
  ----------------------------------- -----------------------------------
  `APPROVED`                          The applicable checks passed

  `PENDING_REVIEW`                    Some details need to be checked
                                      manually

  `REJECTED`                          A validation failure prevents the
                                      invoice from proceeding
  -----------------------------------------------------------------------

## Technology stack

-   **Python** --- application logic
-   **Streamlit** --- user interface
-   **Google Gemini** --- invoice information extraction
-   **PyMuPDF** --- PDF text extraction and page rendering
-   **Tesseract OCR** --- text extraction from scanned PDFs
-   **Pydantic** --- structured data validation
-   **Pandas / RapidFuzz** --- handling and matching reference data
-   **SQLite** --- processing history
-   **pytest** --- automated testing

## Project structure

``` text
InvoiceIQ/
├── app.py
├── config/
│   └── settings.py
├── data/
│   ├── vendors.csv
│   └── purchase_orders.csv
├── sample_invoices/
├── src/
│   ├── database.py
│   ├── decision_engine.py
│   ├── document_processor.py
│   ├── duplicate_detection.py
│   ├── evidence.py
│   ├── extraction.py
│   ├── models.py
│   ├── po_matching.py
│   ├── rules_engine.py
│   ├── validation.py
│   ├── vendor_verification.py
│   └── workflow.py
├── tests/
├── .env.example
├── .gitignore
├── pytest.ini
├── requirements.txt
└── README.md
```

## Run locally

### 1. Clone the repository

``` bash
git clone https://github.com/hittie93/InvoiceIQ
cd InvoiceIQ
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

``` powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**

``` bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

``` bash
pip install -r requirements.txt
```

### 4. Install Tesseract OCR

Install Tesseract OCR for your operating system. On Windows, note the
location of `tesseract.exe`.

### 5. Configure environment variables

Create a `.env` file in the project root using `.env.example` as a
reference.

``` env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=your_supported_gemini_model
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Update the Tesseract path if it is installed in a different location. Do
not commit your `.env` file or API key.

### 6. Start the application

``` bash
streamlit run app.py
```

Open the local URL shown in the terminal, usually
`http://localhost:8501`.

## Run tests

From the project root, run:

``` bash
python -m pytest -v
```

## Deployed this project in Streamlit.io

From the deployed link, run this URL in your browser

``` 
https://invoiceiqq.streamlit.app/
```

