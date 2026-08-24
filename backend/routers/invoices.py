from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse

from backend.schemas.invoices import (
    InvoiceSummary, InvoiceDetail, InvoiceUpdate, ApproveRequest,
    BatchApproveRequest, BatchApproveResult, AuditLogEntry, UploadResult,
)
from backend.schemas.common import OkResponse
from backend.services import invoices_service

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceSummary])
def list_invoices(
    state: str | None = Query(None, description="Needs Review | Problem | Duplicate | Approved | Rejected"),
    property_id: int | None = Query(None),
    category: str | None = Query(None),
    search: str | None = Query(None),
):
    return invoices_service.list_invoices(state=state, property_id=property_id, category=category, search=search)


@router.post("/upload", response_model=list[UploadResult])
async def upload_invoices(files: list[UploadFile] = File(...)):
    results = []
    for f in files:
        content = await f.read()
        results.append(invoices_service.process_upload(f.filename, content))
    return results


@router.post("/batch-approve", response_model=BatchApproveResult)
def batch_approve(payload: BatchApproveRequest):
    return invoices_service.batch_approve(payload.invoice_ids, payload.approved_by)


@router.get("/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: int):
    detail = invoices_service.get_invoice_detail(invoice_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return detail


@router.get("/{invoice_id}/document")
def get_invoice_document(invoice_id: int):
    path = invoices_service.get_invoice_pdf_path(invoice_id)
    if not path:
        raise HTTPException(status_code=404, detail="No PDF available for this invoice")
    return FileResponse(path, media_type="application/pdf")


@router.get("/{invoice_id}/audit", response_model=list[AuditLogEntry])
def get_invoice_audit(invoice_id: int):
    return invoices_service.list_audit_log(invoice_id=invoice_id)


@router.patch("/{invoice_id}", response_model=InvoiceDetail)
def update_invoice(invoice_id: int, payload: InvoiceUpdate):
    detail, errors = invoices_service.update_invoice(invoice_id, payload)
    if not detail:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return detail


@router.post("/{invoice_id}/approve", response_model=OkResponse)
def approve_invoice(invoice_id: int, payload: ApproveRequest):
    ok, error = invoices_service.approve_invoice(invoice_id, payload.approved_by)
    if not ok:
        raise HTTPException(status_code=400, detail=error)
    return OkResponse(ok=True)
