"""
services/invoices_service.py

Mirrors the invoice-state logic that used to live in streamlit_legacy/app.py's
`row_state()` / `is_high_confidence_clean()` — kept here as the single source
of truth so both a future re-scan and the API agree on what "Problem",
"Duplicate", etc. mean.
"""

import json
from pathlib import Path

from engine import db, extraction, validation
from backend.schemas.invoices import (
    InvoiceSummary, InvoiceDetail, DuplicateInfo, InvoiceUpdate,
    BatchApproveResult, AuditLogEntry, UploadResult,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_CONFIDENCE_FIELDS = [
    "vendor", "billing_start", "billing_end", "consumption",
    "consumption_unit", "total_cost",
]


def _row_state(inv_row) -> str:
    if inv_row["duplicate_status"] == "file_duplicate":
        return "Duplicate"
    if inv_row["logical_duplicate_of"] and not inv_row["duplicate_override"]:
        return "Duplicate"
    if inv_row["validation_errors"]:
        return "Problem"
    if inv_row["approved"]:
        return "Approved"
    return "Needs Review"


def _duplicate_reason(inv_row) -> str | None:
    if inv_row["duplicate_status"] == "file_duplicate":
        return "Identical file content already uploaded."
    if inv_row["logical_duplicate_of"]:
        return (
            f"Same vendor + invoice number, or same vendor + amount with an "
            f"overlapping billing period as invoice #{inv_row['logical_duplicate_of']}."
        )
    return None


def _is_high_confidence(inv_row) -> bool:
    if _row_state(inv_row) != "Needs Review":
        return False
    try:
        conf = json.loads(inv_row["field_confidence"] or "{}")
    except Exception:
        return False
    scores = [conf.get(f, 0.0) for f in REQUIRED_CONFIDENCE_FIELDS]
    return bool(scores) and all(s >= 0.6 for s in scores)


def list_invoices(state: str | None = None, property_id: int | None = None,
                   category: str | None = None, search: str | None = None) -> list[InvoiceSummary]:
    conn = db.get_conn()
    try:
        rows = [r for r in db.list_invoices_with_files(conn) if r["filetype"] == "pdf"]
        out = []
        for r in rows:
            row_state = _row_state(r)
            if state and row_state != state:
                continue
            if property_id and r["property_id"] != property_id:
                continue
            if category and r["category"] != category:
                continue
            if search:
                haystack = f"{r['filename']} {r['vendor']} {r['invoice_number']}".lower()
                if search.lower() not in haystack:
                    continue
            out.append(InvoiceSummary(
                id=r["id"], filename=r["filename"], property_id=r["property_id"],
                property_name=r["property_name"], category=r["category"], vendor=r["vendor"],
                invoice_number=r["invoice_number"], billing_start=r["billing_start"],
                billing_end=r["billing_end"], total_cost=r["total_cost"],
                consumption=r["consumption"], consumption_unit=r["consumption_unit"],
                state=row_state, high_confidence=_is_high_confidence(r),
                approved_by=r["approved_by"], last_modified_by=r["last_modified_by"],
            ))
        return out
    finally:
        conn.close()


def get_invoice_detail(invoice_id: int) -> InvoiceDetail | None:
    conn = db.get_conn()
    try:
        inv = db.get_invoice(conn, invoice_id)
        if not inv:
            return None
        sf = next((f for f in db.list_source_files(conn) if f["id"] == inv["source_file_id"]), None)
        if not sf:
            return None

        try:
            confidence = json.loads(inv["field_confidence"] or "{}")
        except Exception:
            confidence = {}
        errors = inv["validation_errors"].split("|") if inv["validation_errors"] else []

        dup_row_style = dict(inv)
        dup_row_style["duplicate_status"] = sf["duplicate_status"]
        state = _row_state(dup_row_style)
        dup_reason = _duplicate_reason(dup_row_style)

        return InvoiceDetail(
            id=inv["id"], source_file_id=inv["source_file_id"], filename=sf["filename"],
            filetype=sf["filetype"], has_pdf=(sf["filetype"] == "pdf" and Path(sf["stored_path"]).exists()),
            raw_text=sf["raw_text"], property_id=inv["property_id"], category=inv["category"],
            vendor=inv["vendor"], invoice_number=inv["invoice_number"],
            billing_start=inv["billing_start"], billing_end=inv["billing_end"],
            consumption=inv["consumption"], consumption_unit=inv["consumption_unit"],
            taxes_fees=inv["taxes_fees"], total_cost=inv["total_cost"], notes=inv["notes"],
            approved=bool(inv["approved"]), approved_by=inv["approved_by"],
            last_modified_by=inv["last_modified_by"], field_confidence=confidence,
            validation_errors=errors,
            duplicate=DuplicateInfo(
                is_duplicate=(state == "Duplicate"), reason=dup_reason,
                matched_invoice_id=inv["logical_duplicate_of"],
            ),
            state=state,
        )
    finally:
        conn.close()


def get_invoice_pdf_path(invoice_id: int) -> Path | None:
    conn = db.get_conn()
    try:
        inv = db.get_invoice(conn, invoice_id)
        if not inv:
            return None
        sf = next((f for f in db.list_source_files(conn) if f["id"] == inv["source_file_id"]), None)
        if not sf or sf["filetype"] != "pdf":
            return None
        path = Path(sf["stored_path"])
        return path if path.exists() else None
    finally:
        conn.close()


def update_invoice(invoice_id: int, payload: InvoiceUpdate) -> tuple[InvoiceDetail | None, list[str]]:
    conn = db.get_conn()
    try:
        inv = db.get_invoice(conn, invoice_id)
        if not inv:
            return None, ["Invoice not found"]

        fields = payload.model_dump(exclude={"duplicate_override", "changed_by"})
        errors = validation.validate_invoice(fields)
        dupes = validation.find_logical_duplicates(conn, fields, exclude_id=invoice_id)

        db.update_invoice(
            conn, invoice_id, fields, validation_errors=errors,
            logical_duplicate_of=dupes[0]["invoice"]["id"] if dupes else None,
            duplicate_override=payload.duplicate_override,
            changed_by=payload.changed_by,
        )
        return get_invoice_detail(invoice_id), errors
    finally:
        conn.close()


def approve_invoice(invoice_id: int, approved_by: str) -> tuple[bool, str | None]:
    conn = db.get_conn()
    try:
        inv = db.get_invoice(conn, invoice_id)
        if not inv:
            return False, "Invoice not found"
        if inv["validation_errors"]:
            return False, "Cannot approve: unresolved validation errors"
        if inv["logical_duplicate_of"] and not inv["duplicate_override"]:
            return False, "Cannot approve: flagged as a likely duplicate (override required)"
        sf = next((f for f in db.list_source_files(conn) if f["id"] == inv["source_file_id"]), None)
        db.approve_invoice(conn, invoice_id, sf["id"], approved_by=approved_by)
        return True, None
    finally:
        conn.close()


def batch_approve(invoice_ids: list[int], approved_by: str) -> BatchApproveResult:
    """
    Approves every invoice in invoice_ids that independently qualifies —
    the server re-derives eligibility itself rather than trusting that the
    caller only submitted invoices it already checked client-side. A client
    (buggy, stale, or malicious) could otherwise submit arbitrary invoice
    ids and have them auto-approved regardless of confidence, validation
    state, or duplicate flags.

    An invoice qualifies only if it has a property assigned, no unresolved
    validation errors, is not an unoverridden duplicate, AND is
    high-confidence on every required field — the same bar shown to the
    user as "clean" in the Invoices queue, re-checked here rather than
    assumed.
    """
    conn = db.get_conn()
    try:
        approved, skipped, skipped_ids = 0, 0, []
        for invoice_id in invoice_ids:
            inv = db.get_invoice(conn, invoice_id)
            if not inv:
                skipped += 1
                skipped_ids.append(invoice_id)
                continue

            sf = next((f for f in db.list_source_files(conn) if f["id"] == inv["source_file_id"]), None)
            if not sf:
                skipped += 1
                skipped_ids.append(invoice_id)
                continue

            row_for_checks = dict(inv)
            row_for_checks["duplicate_status"] = sf["duplicate_status"]

            qualifies = (
                bool(inv["property_id"])
                and not inv["validation_errors"]
                and not (inv["logical_duplicate_of"] and not inv["duplicate_override"])
                and _is_high_confidence(row_for_checks)
            )
            if not qualifies:
                skipped += 1
                skipped_ids.append(invoice_id)
                continue

            db.approve_invoice(conn, invoice_id, sf["id"], approved_by=approved_by)
            approved += 1
        return BatchApproveResult(approved=approved, skipped=skipped, skipped_ids=skipped_ids)
    finally:
        conn.close()


def list_audit_log(invoice_id: int | None = None) -> list[AuditLogEntry]:
    conn = db.get_conn()
    try:
        return [AuditLogEntry(**dict(r)) for r in db.list_audit_log(conn, invoice_id=invoice_id)]
    finally:
        conn.close()


def process_upload(filename: str, file_bytes: bytes) -> UploadResult:
    conn = db.get_conn()
    try:
        fhash = extraction.file_fingerprint(file_bytes)
        existing = db.get_source_file_by_hash(conn, fhash)
        if existing:
            return UploadResult(filename=filename, status="duplicate_skipped",
                                 message=f"Identical to already-uploaded '{existing['filename']}'")

        stored_path = UPLOAD_DIR / f"{fhash[:12]}_{filename}"
        stored_path.write_bytes(file_bytes)

        if filename.lower().endswith(".pdf"):
            text, has_text = extraction.extract_pdf_text(file_bytes)
            sf_id = db.insert_source_file(conn, filename, fhash, "pdf", str(stored_path), text)
            fields, confidence = extraction.parse_invoice_fields(text)
            inv_id = db.insert_draft_invoice(conn, sf_id, fields, confidence)
            errors = validation.validate_invoice(fields)
            db.update_invoice(conn, inv_id, fields, validation_errors=errors, changed_by="extraction")
            msg = None if has_text else "No extractable text found — likely scanned, needs OCR or manual entry."
            return UploadResult(filename=filename, status="created", invoice_id=inv_id,
                                 source_file_id=sf_id, message=msg)
        else:
            try:
                df_preview = extraction.read_tabular_file(file_bytes, filename)
                preview_text = df_preview.head(20).to_csv(index=False)
            except Exception as e:
                preview_text = f"Could not parse file: {e}"
            sf_id = db.insert_source_file(conn, filename, fhash, "tabular", str(stored_path), preview_text)
            db.set_source_file_status(conn, sf_id, "approved")
            return UploadResult(filename=filename, status="tabular_stored", source_file_id=sf_id)
    finally:
        conn.close()
