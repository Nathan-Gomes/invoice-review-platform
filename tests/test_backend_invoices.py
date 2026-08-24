"""
Backend API tests (end-to-end, via FastAPI's TestClient) for invoice
duplicate handling. Run with: pytest tests/test_backend_invoices.py

These exercise the real HTTP layer (routers -> services -> engine -> sqlite),
not just the engine directly, so a bug in how a service translates engine
output into a response (like the duplicate-update KeyError below) gets
caught even when the underlying engine function is correct.
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_backend.db")
    db.init_db()

    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


def _seed_property_and_conn(client):
    conn = db.get_conn()
    db.add_property(conn, "Cedar Place", units=40)
    pid = db.list_properties(conn)[0]["id"]
    conn.close()
    return pid


def test_updating_invoice_that_matches_a_duplicate_does_not_crash(client):
    """
    Regression test: find_logical_duplicates() returns a list of
    {"invoice": Row, "reason": str} dicts (so the UI can explain *why*
    something is a duplicate), but the invoice-update service previously did
    `dupes[0]["id"]` — a KeyError, since "id" isn't a top-level key on that
    dict. The invoice's id is nested at dupes[0]["invoice"]["id"].
    """
    pid = _seed_property_and_conn(client)

    conn = db.get_conn()
    sf1 = db.insert_source_file(conn, "inv1.pdf", "h1", "pdf", "/tmp/x", "text")
    fields1 = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-001", "billing_start": "2026-01-01", "billing_end": "2026-01-31",
        "consumption": 1000, "consumption_unit": "gallons", "total_cost": 400.0,
    }
    inv1_id = db.insert_draft_invoice(conn, sf1, fields1)
    db.update_invoice(conn, inv1_id, fields1)
    db.approve_invoice(conn, inv1_id, sf1)

    sf2 = db.insert_source_file(conn, "inv2.pdf", "h2", "pdf", "/tmp/y", "text")
    fields2 = dict(fields1, invoice_number="W-001")
    inv2_id = db.insert_draft_invoice(conn, sf2, fields2)
    conn.close()

    payload = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-001", "billing_start": "2026-01-01", "billing_end": "2026-01-31",
        "consumption": 1000, "consumption_unit": "gallons", "taxes_fees": None,
        "total_cost": 400.0, "notes": "", "duplicate_override": False, "changed_by": "test",
    }
    response = client.patch(f"/api/invoices/{inv2_id}", json=payload)

    assert response.status_code == 200, f"Expected success, got {response.status_code}: {response.text}"
    detail = response.json()
    assert detail["duplicate"]["is_duplicate"] is True
    assert detail["duplicate"]["matched_invoice_id"] == inv1_id
    assert "invoice #" in detail["duplicate"]["reason"].lower()


def test_updating_invoice_with_overlapping_period_duplicate_does_not_crash(client):
    """Same crash class, triggered via the other duplicate-match path (same
    vendor + amount + overlapping billing period, rather than same invoice number)."""
    pid = _seed_property_and_conn(client)

    conn = db.get_conn()
    sf1 = db.insert_source_file(conn, "inv1.pdf", "h1", "pdf", "/tmp/x", "text")
    fields1 = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-001", "billing_start": "2026-01-01", "billing_end": "2026-01-31",
        "consumption": 1000, "consumption_unit": "gallons", "total_cost": 400.0,
    }
    inv1_id = db.insert_draft_invoice(conn, sf1, fields1)
    db.update_invoice(conn, inv1_id, fields1)
    db.approve_invoice(conn, inv1_id, sf1)

    sf2 = db.insert_source_file(conn, "inv2.pdf", "h2", "pdf", "/tmp/y", "text")
    fields2 = dict(fields1, invoice_number="W-002", billing_start="2026-01-15", billing_end="2026-02-15")
    inv2_id = db.insert_draft_invoice(conn, sf2, fields2)
    conn.close()

    payload = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-002", "billing_start": "2026-01-15", "billing_end": "2026-02-15",
        "consumption": 1000, "consumption_unit": "gallons", "taxes_fees": None,
        "total_cost": 400.0, "notes": "", "duplicate_override": False, "changed_by": "test",
    }
    response = client.patch(f"/api/invoices/{inv2_id}", json=payload)

    assert response.status_code == 200, f"Expected success, got {response.status_code}: {response.text}"
    detail = response.json()
    assert detail["duplicate"]["is_duplicate"] is True
    assert detail["duplicate"]["matched_invoice_id"] == inv1_id


def test_updating_invoice_with_no_duplicate_still_works(client):
    """Non-duplicate updates must keep working normally (no regression from the fix)."""
    pid = _seed_property_and_conn(client)

    conn = db.get_conn()
    sf = db.insert_source_file(conn, "inv1.pdf", "h1", "pdf", "/tmp/x", "text")
    fields = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-100", "billing_start": "2026-01-01", "billing_end": "2026-01-31",
        "consumption": 1000, "consumption_unit": "gallons", "total_cost": 400.0,
    }
    inv_id = db.insert_draft_invoice(conn, sf, fields)
    conn.close()

    payload = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-100", "billing_start": "2026-01-01", "billing_end": "2026-01-31",
        "consumption": 1000, "consumption_unit": "gallons", "taxes_fees": None,
        "total_cost": 400.0, "notes": "", "duplicate_override": False, "changed_by": "test",
    }
    response = client.patch(f"/api/invoices/{inv_id}", json=payload)

    assert response.status_code == 200
    detail = response.json()
    assert detail["duplicate"]["is_duplicate"] is False
    assert detail["duplicate"]["matched_invoice_id"] is None


def test_batch_approve_rejects_low_confidence_invoice_even_if_client_submits_it(client):
    """
    Regression test: the batch-approve endpoint must independently verify
    confidence server-side, not trust that the client only submitted
    invoices it already checked. Constructs an invoice that PASSES
    validation (all fields present, no errors) but has genuinely low stored
    confidence scores — e.g. a human manually completed a sparse extraction
    via Review, which fills in the fields but doesn't retroactively raise
    the original extraction confidence. A client (buggy or malicious)
    submitting this invoice's id directly to /api/invoices/batch-approve
    must have it skipped, not silently auto-approved.
    """
    pid = _seed_property_and_conn(client)

    conn = db.get_conn()
    sf = db.insert_source_file(conn, "weird_layout.pdf", "h1", "pdf", "/tmp/x", "garbled text")
    fields = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-999", "billing_start": "2026-01-01", "billing_end": "2026-01-31",
        "consumption": 1000, "consumption_unit": "gallons", "total_cost": 400.0,
    }
    low_confidence = {k: 0.1 for k in fields}
    inv_id = db.insert_draft_invoice(conn, sf, fields, low_confidence)
    db.update_invoice(conn, inv_id, fields, validation_errors=[])  # passes validation
    conn.close()

    response = client.post(
        "/api/invoices/batch-approve",
        json={"invoice_ids": [inv_id], "approved_by": "malicious_or_buggy_client"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["approved"] == 0
    assert result["skipped"] == 1
    assert inv_id in result["skipped_ids"]

    conn = db.get_conn()
    inv = db.get_invoice(conn, inv_id)
    conn.close()
    assert bool(inv["approved"]) is False


def test_batch_approve_accepts_genuinely_high_confidence_invoice(client):
    """No false-positive skipping: a genuinely clean, high-confidence,
    valid, non-duplicate invoice must still be approved."""
    pid = _seed_property_and_conn(client)

    conn = db.get_conn()
    sf = db.insert_source_file(conn, "clean.pdf", "h_clean", "pdf", "/tmp/z", "clean text")
    fields = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-CLEAN", "billing_start": "2026-02-01", "billing_end": "2026-02-28",
        "consumption": 1000, "consumption_unit": "gallons", "total_cost": 400.0,
    }
    high_confidence = {k: 0.9 for k in fields}
    inv_id = db.insert_draft_invoice(conn, sf, fields, high_confidence)
    db.update_invoice(conn, inv_id, fields, validation_errors=[])
    conn.close()

    response = client.post(
        "/api/invoices/batch-approve",
        json={"invoice_ids": [inv_id], "approved_by": "legit_client"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["approved"] == 1
    assert result["skipped"] == 0

    conn = db.get_conn()
    inv = db.get_invoice(conn, inv_id)
    conn.close()
    assert bool(inv["approved"]) is True
    assert inv["approved_by"] == "legit_client"


def test_batch_approve_rejects_duplicate_without_override(client):
    """A duplicate invoice must not slip through batch-approve without an
    explicit override, even if it happens to be high-confidence."""
    pid = _seed_property_and_conn(client)

    conn = db.get_conn()
    sf1 = db.insert_source_file(conn, "inv1.pdf", "h1", "pdf", "/tmp/x", "text")
    fields1 = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-DUP", "billing_start": "2026-03-01", "billing_end": "2026-03-31",
        "consumption": 1000, "consumption_unit": "gallons", "total_cost": 400.0,
    }
    inv1_id = db.insert_draft_invoice(conn, sf1, fields1)
    db.update_invoice(conn, inv1_id, fields1)
    db.approve_invoice(conn, inv1_id, sf1)

    sf2 = db.insert_source_file(conn, "inv2.pdf", "h2", "pdf", "/tmp/y", "text")
    high_confidence = {k: 0.9 for k in fields1}
    inv2_id = db.insert_draft_invoice(conn, sf2, fields1, high_confidence)
    from engine import validation
    dupes = validation.find_logical_duplicates(conn, fields1, exclude_id=inv2_id)
    db.update_invoice(conn, inv2_id, fields1, validation_errors=[],
                       logical_duplicate_of=dupes[0]["invoice"]["id"] if dupes else None)
    conn.close()

    response = client.post(
        "/api/invoices/batch-approve",
        json={"invoice_ids": [inv2_id], "approved_by": "legit_client"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["approved"] == 0
    assert result["skipped"] == 1
