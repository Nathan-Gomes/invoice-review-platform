"""
schemas/invoices.py
"""

from typing import Optional
from pydantic import BaseModel


class InvoiceSummary(BaseModel):
    id: int
    filename: str
    property_id: Optional[int] = None
    property_name: Optional[str] = None
    category: str
    vendor: str
    invoice_number: Optional[str] = None
    billing_start: Optional[str] = None
    billing_end: Optional[str] = None
    total_cost: Optional[float] = None
    consumption: Optional[float] = None
    consumption_unit: Optional[str] = None
    state: str  # Needs Review | Problem | Duplicate | Approved | Rejected
    high_confidence: bool = False
    approved_by: Optional[str] = None
    last_modified_by: Optional[str] = None


class FieldConfidence(BaseModel):
    field: str
    value: Optional[str] = None
    confidence: float = 0.0


class DuplicateInfo(BaseModel):
    is_duplicate: bool
    reason: Optional[str] = None
    matched_invoice_id: Optional[int] = None


class InvoiceDetail(BaseModel):
    id: int
    source_file_id: int
    filename: str
    filetype: str
    has_pdf: bool
    raw_text: Optional[str] = None
    property_id: Optional[int] = None
    category: str
    vendor: str
    invoice_number: Optional[str] = None
    billing_start: Optional[str] = None
    billing_end: Optional[str] = None
    consumption: Optional[float] = None
    consumption_unit: Optional[str] = None
    taxes_fees: Optional[float] = None
    total_cost: Optional[float] = None
    notes: Optional[str] = None
    approved: bool
    approved_by: Optional[str] = None
    last_modified_by: Optional[str] = None
    field_confidence: dict[str, float] = {}
    validation_errors: list[str] = []
    duplicate: DuplicateInfo
    state: str


class InvoiceUpdate(BaseModel):
    property_id: Optional[int] = None
    category: str
    vendor: str
    invoice_number: str = ""
    billing_start: str = ""
    billing_end: str = ""
    consumption: Optional[float] = None
    consumption_unit: str = ""
    taxes_fees: Optional[float] = None
    total_cost: Optional[float] = None
    notes: str = ""
    duplicate_override: bool = False
    changed_by: str = ""


class ApproveRequest(BaseModel):
    approved_by: str = ""


class BatchApproveRequest(BaseModel):
    invoice_ids: list[int]
    approved_by: str = ""


class BatchApproveResult(BaseModel):
    approved: int
    skipped: int
    skipped_ids: list[int] = []


class AuditLogEntry(BaseModel):
    id: int
    invoice_id: int
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: Optional[str] = None
    changed_at: str


class UploadResult(BaseModel):
    filename: str
    status: str  # "created" | "duplicate_skipped" | "tabular_stored"
    invoice_id: Optional[int] = None
    source_file_id: Optional[int] = None
    message: Optional[str] = None
