"""
Audit log / accountability tests. Run with: pytest tests/test_audit_log.py
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    c = db.get_conn()
    db.add_property(c, "Cedar Place", units=40)
    return c


def _seed_invoice(conn, pid):
    sf = db.insert_source_file(conn, "inv.pdf", "h1", "pdf", "/tmp/x", "text")
    fields = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-1", "billing_start": "2026-01-01", "billing_end": "2026-01-31",
        "consumption": 1000, "consumption_unit": "gallons", "total_cost": 400.0,
    }
    inv_id = db.insert_draft_invoice(conn, sf, fields)
    return sf, inv_id, fields


def test_noop_update_creates_no_audit_entries(conn):
    pid = db.list_properties(conn)[0]["id"]
    sf, inv_id, fields = _seed_invoice(conn, pid)
    db.update_invoice(conn, inv_id, fields, changed_by="nathan")
    assert db.list_audit_log(conn, invoice_id=inv_id) == []


def test_real_change_logs_exactly_the_changed_fields(conn):
    pid = db.list_properties(conn)[0]["id"]
    sf, inv_id, fields = _seed_invoice(conn, pid)
    db.update_invoice(conn, inv_id, fields, changed_by="nathan")  # baseline, no-op

    changed = dict(fields, total_cost=450.0, vendor="Cedar Water Utility")
    db.update_invoice(conn, inv_id, changed, changed_by="nathan")

    log = db.list_audit_log(conn, invoice_id=inv_id)
    fields_changed = {row["field"] for row in log}
    assert fields_changed == {"total_cost", "vendor"}
    assert all(row["changed_by"] == "nathan" for row in log)


def test_numeric_string_vs_float_not_flagged_as_change(conn):
    """1000 and 1000.0 are the same value and shouldn't create a spurious entry."""
    pid = db.list_properties(conn)[0]["id"]
    sf, inv_id, fields = _seed_invoice(conn, pid)
    db.update_invoice(conn, inv_id, fields, changed_by="nathan")

    same_value_different_type = dict(fields, consumption=1000.0)
    db.update_invoice(conn, inv_id, same_value_different_type, changed_by="nathan")
    assert db.list_audit_log(conn, invoice_id=inv_id) == []


def test_none_vs_empty_string_not_flagged_as_change(conn):
    pid = db.list_properties(conn)[0]["id"]
    sf, inv_id, fields = _seed_invoice(conn, pid)
    fields_with_empty_notes = dict(fields, notes="")
    db.update_invoice(conn, inv_id, fields_with_empty_notes, changed_by="nathan")

    fields_with_none_notes = dict(fields, notes=None)
    db.update_invoice(conn, inv_id, fields_with_none_notes, changed_by="nathan")
    assert db.list_audit_log(conn, invoice_id=inv_id) == []


def test_approve_records_approved_by_and_logs_it(conn):
    pid = db.list_properties(conn)[0]["id"]
    sf, inv_id, fields = _seed_invoice(conn, pid)
    db.update_invoice(conn, inv_id, fields, changed_by="nathan")
    db.approve_invoice(conn, inv_id, sf, approved_by="nathan")

    inv = db.get_invoice(conn, inv_id)
    assert inv["approved_by"] == "nathan"
    assert inv["last_modified_by"] == "nathan"

    log = db.list_audit_log(conn, invoice_id=inv_id)
    approval_entries = [r for r in log if r["field"] == "approved"]
    assert len(approval_entries) == 1
    assert approval_entries[0]["old_value"] == "0"
    assert approval_entries[0]["new_value"] == "1"
