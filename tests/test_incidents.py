"""
Incident triage regression tests. Run with: pytest tests/test_incidents.py
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import db
from engine import anomalies
from engine import incidents


@pytest.fixture
def leak_conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    conn = db.get_conn()
    db.add_property(conn, "Cedar Place", units=40)
    pid = db.list_properties(conn)[0]["id"]

    def add_invoice(month, consumption, cost, occupied):
        sf = db.insert_source_file(conn, f"w_{month}.pdf", f"h_{month}", "pdf", "/tmp/x", "t")
        fields = {
            "property_id": pid, "category": "Water", "vendor": "Cedar Water",
            "invoice_number": f"W-{month}", "billing_start": f"{month}-01", "billing_end": f"{month}-28",
            "consumption": consumption, "consumption_unit": "gallons", "total_cost": cost,
        }
        inv_id = db.insert_draft_invoice(conn, sf, fields)
        db.update_invoice(conn, inv_id, fields)
        db.approve_invoice(conn, inv_id, sf)
        db.upsert_occupancy(conn, pid, month, occupied, 40 - occupied)

    for m in range(1, 13):
        add_invoice(f"2025-{m:02d}", 36 * 1000, 36 * 1000 * 0.01, 36)
    add_invoice("2026-01", 36 * 1000, 36 * 1000 * 0.01, 36)
    add_invoice("2026-02", 36 * 1300, 36 * 1300 * 0.01, 36)
    add_invoice("2026-03", 36 * 1300, 36 * 1300 * 0.01, 36)

    return conn, pid


def test_multiple_rule_hits_collapse_into_one_incident(leak_conn):
    conn, pid = leak_conn
    raw = anomalies.scan_all(conn, only_latest_month=True)
    assert len(raw) > 1  # multiple rules fire for this leak

    grouped = incidents.get_triaged_incidents(conn, only_latest_month=True)
    assert len(grouped) == 1
    assert grouped[0]["property_name"] == "Cedar Place"
    assert grouped[0]["category"] == "Water"
    assert set(grouped[0]["rules"]) >= {"usage_above_baseline", "sustained_elevated_usage"}


def test_incident_tier_is_critical_for_strong_high_impact(leak_conn):
    conn, pid = leak_conn
    grouped = incidents.get_triaged_incidents(conn, only_latest_month=True)
    assert grouped[0]["tier"] == "Critical"
    assert grouped[0]["severity"] == "High"
    assert grouped[0]["confidence"] == "Strong"


def test_incident_annualized_impact_uses_latest_month_not_sum(leak_conn):
    """Multiple rules on the same month must not have their observed_excess
    summed — that would multiply-count the same dollars several times."""
    conn, pid = leak_conn
    grouped = incidents.get_triaged_incidents(conn, only_latest_month=True)
    incident = grouped[0]
    # monthly excess was $108 in the underlying scenario -> annualized = $1296
    assert incident["annualized_impact"] == pytest.approx(1296.0, rel=0.05)


def test_dismiss_incident_suppresses_future_scans(leak_conn):
    conn, pid = leak_conn
    grouped = incidents.get_triaged_incidents(conn, only_latest_month=True)
    assert len(grouped) == 1

    incidents.dismiss_incident(conn, grouped[0], reason="Already being fixed")

    grouped_after = incidents.get_triaged_incidents(conn, only_latest_month=True)
    assert grouped_after == []


def test_dismissing_one_property_category_does_not_affect_others(leak_conn):
    conn, pid = leak_conn
    db.add_property(conn, "Oak Towers", units=20)
    oak_id = db.list_properties(conn)[1]["id"]

    def add_oak_invoice(month, consumption, cost, occupied):
        sf = db.insert_source_file(conn, f"oak_{month}.pdf", f"hoak_{month}", "pdf", "/tmp/x", "t")
        fields = {
            "property_id": oak_id, "category": "Water", "vendor": "Oak Water",
            "invoice_number": f"OAK-{month}", "billing_start": f"{month}-01", "billing_end": f"{month}-28",
            "consumption": consumption, "consumption_unit": "gallons", "total_cost": cost,
        }
        inv_id = db.insert_draft_invoice(conn, sf, fields)
        db.update_invoice(conn, inv_id, fields)
        db.approve_invoice(conn, inv_id, sf)
        db.upsert_occupancy(conn, oak_id, month, occupied, 20 - occupied)

    for m in range(1, 13):
        add_oak_invoice(f"2025-{m:02d}", 18 * 1000, 18 * 1000 * 0.01, 18)
    add_oak_invoice("2026-01", 18 * 1000, 18 * 1000 * 0.01, 18)
    add_oak_invoice("2026-02", 18 * 1400, 18 * 1400 * 0.01, 18)
    add_oak_invoice("2026-03", 18 * 1400, 18 * 1400 * 0.01, 18)

    grouped = incidents.get_triaged_incidents(conn, only_latest_month=True)
    assert len(grouped) == 2

    cedar_incident = next(i for i in grouped if i["property_name"] == "Cedar Place")
    incidents.dismiss_incident(conn, cedar_incident, reason="Confirmed")

    grouped_after = incidents.get_triaged_incidents(conn, only_latest_month=True)
    assert len(grouped_after) == 1
    assert grouped_after[0]["property_name"] == "Oak Towers"


def test_create_finding_from_incident_links_source_invoices(leak_conn):
    conn, pid = leak_conn
    grouped = incidents.get_triaged_incidents(conn, only_latest_month=True)
    finding_id = incidents.create_finding_from_incident(conn, grouped[0])

    findings = db.list_findings(conn)
    assert len(findings) == 1
    f = findings[0]
    assert f["id"] == finding_id
    assert f["property_id"] == pid
    assert f["source_invoice_ids"]  # not empty -> traceable to at least one invoice


def test_missing_occupancy_only_incident_is_informational(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test6.db")
    db.init_db()
    conn = db.get_conn()
    db.add_property(conn, "New Building", units=20)
    pid = db.list_properties(conn)[0]["id"]

    sf = db.insert_source_file(conn, "w1.pdf", "h1", "pdf", "/tmp/x", "t")
    fields = {
        "property_id": pid, "category": "Water", "vendor": "Test Water",
        "invoice_number": "W-1", "billing_start": "2026-01-01", "billing_end": "2026-01-28",
        "consumption": 10000, "consumption_unit": "gallons", "total_cost": 100.0,
    }
    inv_id = db.insert_draft_invoice(conn, sf, fields)
    db.update_invoice(conn, inv_id, fields)
    db.approve_invoice(conn, inv_id, sf)
    # deliberately no occupancy entered

    grouped = incidents.get_triaged_incidents(conn, only_latest_month=True)
    assert len(grouped) == 1
    assert grouped[0]["tier"] == "Informational"
    assert grouped[0]["rules"] == ["missing_occupancy"]


def test_new_months_missing_occupancy_does_not_mask_recent_real_incident(leak_conn):
    """
    Regression test: if a new invoice for the latest month is approved before
    occupancy data exists for it, the resulting missing_occupancy flag must
    not hide a real, still-active incident from a recent prior month (here,
    the leak in 2026-03). They should combine into one incident instead.
    """
    conn, pid = leak_conn

    sf = db.insert_source_file(conn, "water_2026-04.pdf", "hash_2026-04_v2", "pdf", "/tmp/x", "text")
    fields = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-2026-04-v2", "billing_start": "2026-04-01", "billing_end": "2026-04-28",
        "consumption": 36000, "consumption_unit": "gallons", "total_cost": 360.0,
    }
    inv_id = db.insert_draft_invoice(conn, sf, fields)
    db.update_invoice(conn, inv_id, fields)
    db.approve_invoice(conn, inv_id, sf)
    # deliberately no occupancy for 2026-04

    triaged = incidents.get_triaged_incidents(conn)
    cedar_water = next(
        (inc for inc in triaged if inc["property_id"] == pid and inc["category"] == "Water"), None
    )
    assert cedar_water is not None
    assert "missing_occupancy" in cedar_water["rules"]
    assert "usage_above_baseline" in cedar_water["rules"] or "sustained_elevated_usage" in cedar_water["rules"]
    assert cedar_water["tier"] == "Critical"
    assert cedar_water["annualized_impact"] > 0
