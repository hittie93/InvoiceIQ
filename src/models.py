
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class TaxComponent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tax_name: Optional[str] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    currency: Optional[str] = None


class InvoiceLineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: Optional[str] = None
    hsn_sac_code: Optional[str] = None

    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None

    unit_price: Optional[float] = None
    unit_price_currency: Optional[str] = None

    taxable_value: Optional[float] = None
    taxable_value_currency: Optional[str] = None

    tax_amount: Optional[float] = None
    tax_currency: Optional[str] = None

    line_total: Optional[float] = None
    line_total_currency: Optional[str] = None


class InvoiceData(BaseModel):
    """Normalised invoice fields extracted from a source document."""

    model_config = ConfigDict(extra="ignore")

    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_tax_id: Optional[str] = None

    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_number: Optional[str] = None

    # Currency of the final payable invoice amount.
    currency: Optional[str] = "INR"

    subtotal: Optional[float] = None
    subtotal_currency: Optional[str] = None

    tax_amount: Optional[float] = None
    tax_currency: Optional[str] = None

    total_amount: Optional[float] = None
    total_amount_currency: Optional[str] = None

    # Foreign currency conversion information.
    source_currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    exchange_rate_description: Optional[str] = None

    # Additional tax details.
    tax_components: list[TaxComponent] = Field(default_factory=list)

    line_items: list[InvoiceLineItem] = Field(default_factory=list)

    extraction_notes: list[str] = Field(default_factory=list)


class CheckResult(BaseModel):
    name: str
    status: str
    message: str
    details: dict = Field(default_factory=dict)


class WorkflowResult(BaseModel):
    run_id: str
    decision: str
    reason: str
    invoice: dict
    checks: list[CheckResult]
    variance_percent: Optional[float] = None
    human_review_required: bool = False
    source_text_preview: str = ""
    field_evidence: dict = Field(default_factory=dict)
