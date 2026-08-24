"""
Analysis formula tests (item 15). Run with: pytest tests/test_analysis.py

Builds a synthetic 15-month billing history for one property (12 stable
months + a sustained usage increase in the last 2), and checks the
expected-cost/observed-excess math and anomaly triggers against known
hand-calculated values.
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import db
from engine import analysis
from engine import anomalies


@pytest.fixture
def leak_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    conn = db.get_conn()
    db.add_property(conn, "Cedar Place", units=40)
    pid = db.list_properties(conn)[0]["id"]

    def add_invoice(month, consumption, cost, occupied):
        sf = db.insert_source_file(conn, f"water_{month}.pdf", f"hash_{month}", "pdf", "/tmp/x", "text")
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
        month = f"2025-{m:02d}"
        add_invoice(month, consumption=36 * 1000, cost=36 * 1000 * 0.01, occupied=36)

    add_invoice("2026-01", consumption=36 * 1000, cost=36 * 1000 * 0.01, occupied=36)
    add_invoice("2026-02", consumption=36 * 1300, cost=36 * 1300 * 0.01, occupied=36)
    add_invoice("2026-03", consumption=36 * 1300, cost=36 * 1300 * 0.01, occupied=36)

    return conn, pid


def test_baseline_usage_excludes_current_month(leak_scenario):
    conn, pid = leak_scenario
    baseline = analysis.compute_baseline(conn, pid, "Water", "2026-03")
    # baseline should reflect the stable 1000 gal/unit months, not the leak
    # months. Fixture uses a fixed 27-day billing period throughout, so
    # usage_per_unit_per_day * days recovers the per-period figure exactly.
    assert baseline["usage_per_unit_per_day"] * 27 == pytest.approx(1000.0, rel=0.05)


def test_expected_cost_and_observed_excess(leak_scenario):
    conn, pid = leak_scenario
    metrics = analysis.compute_property_month_metrics(conn, pid, "Water", "2026-03")

    assert metrics["total_cost"] == pytest.approx(468.0)
    assert metrics["occupied_units"] == 36
    assert metrics["consumption_per_occupied_unit"] == pytest.approx(1300.0)
    # expected = baseline_usage(1000) * occupied(36) * baseline_rate(0.01) = 360
    assert metrics["expected_cost"] == pytest.approx(360.0, rel=0.05)
    assert metrics["observed_excess"] == pytest.approx(108.0, rel=0.05)


def test_yoy_variance_matches_hand_calculation(leak_scenario):
    conn, pid = leak_scenario
    metrics = analysis.compute_property_month_metrics(conn, pid, "Water", "2026-03")
    # 2025-03 was a stable month at 360.0; 2026-03 is 468.0 -> +30%
    assert metrics["yoy_variance_pct"] == pytest.approx(30.0, rel=0.05)


def test_stable_month_has_no_anomalies(leak_scenario):
    conn, pid = leak_scenario
    found = anomalies.check_property_month(conn, pid, "Water", "2026-01")
    assert found == []


def test_leak_month_triggers_usage_and_sustained_rules(leak_scenario):
    conn, pid = leak_scenario
    found = anomalies.check_property_month(conn, pid, "Water", "2026-03")
    rules = {a["rule"] for a in found}
    assert "usage_above_baseline" in rules
    assert "sustained_elevated_usage" in rules
    # every anomaly must name a cause and a severity — nothing left blank
    for a in found:
        assert a["severity"] in ("Low", "Medium", "High")
        assert a["confidence"] in ("Possible", "Likely", "Strong")
        assert a["cause"] in ("Usage", "Rate", "Occupancy", "Billing", "Unknown")


def test_missing_occupancy_flagged(leak_scenario):
    conn, pid = leak_scenario
    sf = db.insert_source_file(conn, "water_2026-04.pdf", "hash_2026-04", "pdf", "/tmp/x", "text")
    fields = {
        "property_id": pid, "category": "Water", "vendor": "Cedar Water",
        "invoice_number": "W-2026-04", "billing_start": "2026-04-01", "billing_end": "2026-04-28",
        "consumption": 40000, "consumption_unit": "gallons", "total_cost": 400.0,
    }
    inv_id = db.insert_draft_invoice(conn, sf, fields)
    db.update_invoice(conn, inv_id, fields)
    db.approve_invoice(conn, inv_id, sf)
    # deliberately no occupancy entered for 2026-04

    found = anomalies.check_property_month(conn, pid, "Water", "2026-04")
    rules = {a["rule"] for a in found}
    assert "missing_occupancy" in rules


def test_billing_day_normalization_prevents_false_usage_flag(tmp_path, monkeypatch):
    """A longer billing period (36 days vs. the usual 28) naturally has more
    raw consumption per unit — but per-day usage should show this is flat,
    not a real usage increase, and 'cause' must not be flagged as Usage."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test2.db")
    db.init_db()
    conn = db.get_conn()
    db.add_property(conn, "Cedar Place", units=40)
    pid = db.list_properties(conn)[0]["id"]

    def add_invoice(month, start, end, consumption, cost, occupied):
        sf = db.insert_source_file(conn, f"w_{month}.pdf", f"h_{month}", "pdf", "/tmp/x", "t")
        fields = {
            "property_id": pid, "category": "Water", "vendor": "Cedar Water",
            "invoice_number": f"W-{month}", "billing_start": start, "billing_end": end,
            "consumption": consumption, "consumption_unit": "gallons", "total_cost": cost,
        }
        inv_id = db.insert_draft_invoice(conn, sf, fields)
        db.update_invoice(conn, inv_id, fields)
        db.approve_invoice(conn, inv_id, sf)
        db.upsert_occupancy(conn, pid, month, occupied, 40 - occupied)

    for m in range(1, 13):
        month = f"2025-{m:02d}"
        add_invoice(month, f"{month}-01", f"{month}-28", 36 * 1000, 36 * 1000 * 0.01, 36)

    add_invoice("2026-01", "2026-01-01", "2026-02-06", 36 * 1000 * (36 / 28), 36 * 1000 * (36 / 28) * 0.01, 36)

    metrics = analysis.compute_property_month_metrics(conn, pid, "Water", "2026-01")
    assert metrics["billing_days"] == 36
    assert metrics["usage_pct_over_baseline"] == pytest.approx(0.0, abs=5.0)
    assert metrics["cause"] != "Usage"


def test_same_season_yoy_used_with_enough_history(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test3.db")
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

    for year in (2023, 2024, 2025):
        for m in range(1, 13):
            add_invoice(f"{year}-{m:02d}", 36 * 1000, 36 * 1000 * 0.01, 36)
    add_invoice("2026-01", 36 * 1000, 36 * 1000 * 0.01, 36)
    add_invoice("2026-02", 36 * 1300, 36 * 1300 * 0.01, 36)
    add_invoice("2026-03", 36 * 1300, 36 * 1300 * 0.01, 36)

    metrics = analysis.compute_property_month_metrics(conn, pid, "Water", "2026-03")
    assert metrics["baseline_method"] == "same_season_yoy"
    assert metrics["baseline_sample_size"] == 3
    assert metrics["baseline_confidence"] == "Moderate"


def test_insufficient_history_flagged_as_such(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test4.db")
    db.init_db()
    conn = db.get_conn()
    db.add_property(conn, "New Building", units=20)
    pid = db.list_properties(conn)[0]["id"]

    sf = db.insert_source_file(conn, "w_2026-01.pdf", "h1", "pdf", "/tmp/x", "t")
    fields = {
        "property_id": pid, "category": "Water", "vendor": "Test Water",
        "invoice_number": "W-1", "billing_start": "2026-01-01", "billing_end": "2026-01-28",
        "consumption": 10000, "consumption_unit": "gallons", "total_cost": 100.0,
    }
    inv_id = db.insert_draft_invoice(conn, sf, fields)
    db.update_invoice(conn, inv_id, fields)
    db.approve_invoice(conn, inv_id, sf)
    db.upsert_occupancy(conn, pid, "2026-01", 20, 0)

    metrics = analysis.compute_property_month_metrics(conn, pid, "Water", "2026-01")
    assert metrics["baseline_confidence"] == "Insufficient"
    assert "enough history" in metrics["explanation"].lower()


def test_rate_driven_increase_classified_as_rate(tmp_path, monkeypatch):
    """When usage is flat but the effective rate jumps, cause should be Rate, not Usage."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test5.db")
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
    add_invoice("2026-02", 36 * 1000, 36 * 1000 * 0.015, 36)

    metrics = analysis.compute_property_month_metrics(conn, pid, "Water", "2026-02")
    assert metrics["cause"] == "Rate"
    assert "price-driven" in metrics["explanation"].lower()


def test_one_authoritative_baseline_drives_alert_trigger_and_explanation(tmp_path, monkeypatch):
    """
    Regression test for the baseline-consistency bug: a longer billing period
    (36 days vs. the usual 28) naturally has more raw consumption per unit.
    Before the fix, the anomaly rule compared raw per-period consumption
    against a non-day-normalized trailing baseline (a SEPARATE calculation
    from the one driving the explanation), so this longer invoice could
    trip 'usage_above_baseline' even though per-day usage is flat. After the
    fix, both the rule trigger and the explanation read from the same
    compute_baseline() result, so the rule must NOT fire here.
    """
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test6.db")
    db.init_db()
    conn = db.get_conn()
    db.add_property(conn, "Cedar Place", units=40)
    pid = db.list_properties(conn)[0]["id"]

    def add_invoice(month, start, end, consumption, cost, occupied):
        sf = db.insert_source_file(conn, f"w_{month}.pdf", f"h_{month}", "pdf", "/tmp/x", "t")
        fields = {
            "property_id": pid, "category": "Water", "vendor": "Cedar Water",
            "invoice_number": f"W-{month}", "billing_start": start, "billing_end": end,
            "consumption": consumption, "consumption_unit": "gallons", "total_cost": cost,
        }
        inv_id = db.insert_draft_invoice(conn, sf, fields)
        db.update_invoice(conn, inv_id, fields)
        db.approve_invoice(conn, inv_id, sf)
        db.upsert_occupancy(conn, pid, month, occupied, 40 - occupied)

    for m in range(1, 13):
        month = f"2025-{m:02d}"
        add_invoice(month, f"{month}-01", f"{month}-28", 36 * 1000, 36 * 1000 * 0.01, 36)

    # 36-day period instead of the usual 27 — 36/27 = 1.33x more raw
    # consumption for the SAME per-day usage rate. A non-day-normalized
    # baseline comparison would read this as usage up ~33%, well above the
    # 20% default threshold.
    add_invoice("2026-01", "2026-01-01", "2026-02-06", 36 * 1000 * (36 / 27), 36 * 1000 * (36 / 27) * 0.01, 36)

    found = anomalies.check_property_month(conn, pid, "Water", "2026-01")
    rules = {a["rule"] for a in found}
    assert "usage_above_baseline" not in rules, (
        "Longer billing period alone must not trigger a usage anomaly once "
        "the alert trigger uses the same day-normalized baseline as the explanation."
    )

    # And the dollar impact estimate must agree with that same conclusion:
    # since per-day usage is flat, observed_excess should be small/near zero,
    # not inflated by the raw day-count difference.
    metrics = analysis.compute_property_month_metrics(conn, pid, "Water", "2026-01")
    assert metrics["observed_excess"] == pytest.approx(0.0, abs=5.0)
