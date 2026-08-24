"""
Unit conversion regression tests. Run with: pytest tests/test_units.py
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import db, analysis, anomalies, units


def test_ccf_to_therms_conversion():
    # 45.6 CCF should be ~47.3 therms (45.6 * 1.037)
    result = units.normalize_gas_consumption(45.6, "CCF")
    assert result == pytest.approx(45.6 * 1.037)


def test_m3_to_therms_conversion():
    result = units.normalize_gas_consumption(129.0, "m3")
    assert result == pytest.approx(129.0 * 0.3661)


def test_therms_passthrough_identity():
    assert units.normalize_gas_consumption(100.0, "therms") == pytest.approx(100.0)


def test_unrecognized_unit_passes_through_unchanged():
    """gallons/kWh aren't gas units — normalize_gas_consumption must be a
    safe no-op passthrough so it can't accidentally corrupt water/electric math."""
    assert units.normalize_gas_consumption(500.0, "gallons") == 500.0
    assert units.normalize_gas_consumption(500.0, "kWh") == 500.0


def test_none_value_returns_none():
    assert units.normalize_gas_consumption(None, "CCF") is None


@pytest.fixture
def mixed_unit_gas_conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    conn = db.get_conn()
    db.add_property(conn, "Cedar Place", units=40)
    pid = db.list_properties(conn)[0]["id"]

    def add_invoice(month, consumption, unit, cost, occupied):
        sf = db.insert_source_file(conn, f"gas_{month}.pdf", f"hash_{month}", "pdf", "/tmp/x", "text")
        fields = {
            "property_id": pid, "category": "Natural Gas", "vendor": "Metro Gas",
            "invoice_number": f"G-{month}", "billing_start": f"{month}-01", "billing_end": f"{month}-28",
            "consumption": consumption, "consumption_unit": unit, "total_cost": cost,
        }
        inv_id = db.insert_draft_invoice(conn, sf, fields)
        db.update_invoice(conn, inv_id, fields)
        db.approve_invoice(conn, inv_id, sf)
        db.upsert_occupancy(conn, pid, month, occupied, 40 - occupied)

    # 12 stable months billed in CCF: 36 CCF -> ~37.3 therms, at a rate that
    # keeps $/therm roughly constant across the switch below.
    therms_per_unit_target = 1.0  # 1 therm per occupied unit per period, stable
    for m in range(1, 13):
        month = f"2025-{m:02d}"
        ccf_amount = (36 * therms_per_unit_target) / 1.037  # CCF that converts to exactly 36 therms
        add_invoice(month, ccf_amount, "CCF", 36 * 1.20, 36)  # $1.20/therm

    return conn, pid


def test_mixed_gas_units_do_not_falsely_trigger_usage_anomaly(mixed_unit_gas_conn):
    """
    Regression test: before unit conversion was wired in, a property billed
    in CCF for a year and then switched to therms for one period would show
    a spurious ~exact usage change purely from the unit switch (since raw
    CCF and raw therm numbers are close in magnitude but not equal — 1 CCF
    ~= 1.037 therms — a property averaging ~36 therms/period in CCF terms
    would report ~34.7 raw CCF-units, and comparing that raw number against
    a later raw-therms reading would misread a ~3.7% *unit* difference as a
    usage change). After the fix, both get converted to canonical therms
    before comparison, so genuinely flat usage must not fire the rule.
    """
    conn, pid = mixed_unit_gas_conn

    # Same true usage (36 therms) and same $/therm rate, but billed in
    # therms directly instead of CCF this period.
    sf = db.insert_source_file(conn, "gas_2026-01.pdf", "hash_2026-01", "pdf", "/tmp/x", "text")
    fields = {
        "property_id": pid, "category": "Natural Gas", "vendor": "Metro Gas",
        "invoice_number": "G-2026-01", "billing_start": "2026-01-01", "billing_end": "2026-01-28",
        "consumption": 36.0, "consumption_unit": "therms", "total_cost": 36 * 1.20,
    }
    inv_id = db.insert_draft_invoice(conn, sf, fields)
    db.update_invoice(conn, inv_id, fields)
    db.approve_invoice(conn, inv_id, sf)
    db.upsert_occupancy(conn, pid, "2026-01", 36, 4)

    found = anomalies.check_property_month(conn, pid, "Natural Gas", "2026-01")
    rules = {a["rule"] for a in found}
    assert "usage_above_baseline" not in rules
    assert "rate_above_baseline" not in rules

    metrics = analysis.compute_property_month_metrics(conn, pid, "Natural Gas", "2026-01")
    assert metrics["usage_pct_over_baseline"] == pytest.approx(0.0, abs=2.0)
    assert metrics["cause"] not in ("Usage", "Rate")
