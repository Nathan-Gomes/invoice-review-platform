"""
Validation regression tests. Run with: pytest tests/test_validation.py
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import db
from engine import validation


GOOD_INVOICE = {
    "property_id": 1, "category": "Water", "vendor": "Cedar Water",
    "billing_start": "2026-01-01", "billing_end": "2026-01-31",
    "consumption": 45230, "consumption_unit": "gallons", "total_cost": 412.55,
}


def test_valid_invoice_has_no_errors():
    assert validation.validate_invoice(GOOD_INVOICE) == []


def test_end_before_start_is_flagged():
    bad = dict(GOOD_INVOICE, billing_start="2026-02-01", billing_end="2026-01-01")
    errors = validation.validate_invoice(bad)
    assert "Billing end date is before billing start date" in errors


def test_missing_everything_lists_each_required_field_once():
    empty = {k: (None if k != "category" else "") for k in [
        "property_id", "category", "vendor", "billing_start", "billing_end",
        "consumption", "consumption_unit", "total_cost",
    ]}
    errors = validation.validate_invoice(empty)
    # consumption unit should not be flagged twice (loop + explicit check)
    unit_mentions = [e for e in errors if "consumption unit" in e.lower()]
    assert len(unit_mentions) <= 1
    assert "Missing Property" in errors
    assert "Missing consumption" in errors


def test_zero_total_cost_flagged():
    zero_cost = dict(GOOD_INVOICE, total_cost=0)
    errors = validation.validate_invoice(zero_cost)
    assert "Total cost is zero or missing" in errors


def test_zero_consumption_flagged_as_missing():
    """UI number_input defaults to 0.0 rather than None, so zero must be
    treated as missing — otherwise a genuinely blank field silently passes."""
    zero_consumption = dict(GOOD_INVOICE, consumption=0.0)
    errors = validation.validate_invoice(zero_consumption)
    assert "Missing consumption" in errors


@pytest.fixture
def two_properties_conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    conn = db.get_conn()
    db.add_property(conn, "Cedar Place", units=40)
    pid = db.list_properties(conn)[0]["id"]

    sf = db.insert_source_file(conn, "inv1.pdf", "hash1", "pdf", "/tmp/1", "text1")
    fields = dict(GOOD_INVOICE, property_id=pid, invoice_number="WU-001")
    inv_id = db.insert_draft_invoice(conn, sf, fields)
    db.update_invoice(conn, inv_id, fields)
    db.approve_invoice(conn, inv_id, sf)
    return conn, pid


def test_same_invoice_number_flagged_as_duplicate(two_properties_conn):
    conn, pid = two_properties_conn
    fields = dict(GOOD_INVOICE, property_id=pid, invoice_number="WU-001")
    dupes = validation.find_logical_duplicates(conn, fields)
    assert len(dupes) == 1


def test_overlapping_period_same_amount_flagged(two_properties_conn):
    conn, pid = two_properties_conn
    fields = dict(GOOD_INVOICE, property_id=pid, invoice_number="WU-002",
                  billing_start="2026-01-15", billing_end="2026-02-15")
    dupes = validation.find_logical_duplicates(conn, fields)
    assert len(dupes) == 1


def test_different_vendor_not_flagged(two_properties_conn):
    conn, pid = two_properties_conn
    fields = dict(GOOD_INVOICE, property_id=pid, vendor="Totally Different Co",
                  invoice_number="X-999")
    dupes = validation.find_logical_duplicates(conn, fields)
    assert dupes == []


def test_non_overlapping_period_not_flagged(two_properties_conn):
    conn, pid = two_properties_conn
    fields = dict(GOOD_INVOICE, property_id=pid, invoice_number="WU-003",
                  billing_start="2026-03-01", billing_end="2026-03-31")
    dupes = validation.find_logical_duplicates(conn, fields)
    assert dupes == []
