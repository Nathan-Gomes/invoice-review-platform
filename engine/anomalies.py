"""
anomalies.py — Anomaly Rules V1. Transparent, threshold-based rules (no ML),
with thresholds read from Settings so they're editable without a code change.
Every anomaly names the exact rule that triggered it, and carries a
severity/confidence/cause so users can prioritize without reviewing everything.
"""

import statistics
from engine import db as db_module
from engine import analysis


def _thresholds(conn):
    return db_module.get_thresholds(conn)


def check_property_month(conn, property_id, category, month):
    """
    Runs all Anomaly Rules V1 checks for one property/category/month.
    Returns a list of anomaly dicts: {rule, severity, confidence, cause, message, observed_excess}.
    """
    th = _thresholds(conn)
    metrics = analysis.compute_property_month_metrics(conn, property_id, category, month)
    if metrics is None:
        return []

    anomalies = []
    prop = db_module.get_property(conn, property_id)
    prop_name = prop["name"] if prop else f"Property {property_id}"

    # Rule 1: total cost > threshold% above same month last year
    if metrics["yoy_variance_pct"] is not None and metrics["yoy_variance_pct"] > th["yoy_pct"]:
        anomalies.append({
            "rule": "yoy_cost_increase",
            "severity": "High" if metrics["yoy_variance_pct"] > th["yoy_pct"] * 2 else "Medium",
            "confidence": "Likely",
            "cause": metrics.get("cause", "Unknown"),
            "message": (
                f"{prop_name} {category} cost for {month} is "
                f"{metrics['yoy_variance_pct']:.0f}% above the same month last year "
                f"(threshold: {th['yoy_pct']:.0f}%)."
            ),
            "observed_excess": metrics["observed_excess"],
            "metrics": metrics,
        })

    # Rule 2: usage per occupied unit (per day, season-adjusted) > threshold% above baseline
    if metrics["usage_pct_over_baseline"] is not None:
        usage_pct = metrics["usage_pct_over_baseline"]
        if usage_pct > th["usage_pct"]:
            anomalies.append({
                "rule": "usage_above_baseline",
                "severity": "High" if usage_pct > th["usage_pct"] * 1.5 else "Medium",
                "confidence": "Likely" if metrics["baseline_confidence"] != "Insufficient" else "Possible",
                "cause": "Usage",
                "message": (
                    f"{prop_name} {category} usage per occupied unit is {usage_pct:.0f}% "
                    f"above its {'same-season' if metrics['baseline_method'] == 'same_season_yoy' else 'trailing'} "
                    f"baseline (threshold: {th['usage_pct']:.0f}%)."
                ),
                "observed_excess": metrics["observed_excess"],
                "metrics": metrics,
            })

    # Rule 3: effective rate > threshold% above baseline rate (price, not usage, driving cost)
    if metrics["rate_pct_over_baseline"] is not None:
        rate_pct = metrics["rate_pct_over_baseline"]
        if rate_pct > th["rate_pct"]:
            anomalies.append({
                "rule": "rate_above_baseline",
                "severity": "Medium",
                "confidence": "Likely" if metrics["baseline_confidence"] != "Insufficient" else "Possible",
                "cause": "Rate",
                "message": (
                    f"{prop_name} {category} effective rate is {rate_pct:.0f}% above baseline "
                    f"(threshold: {th['rate_pct']:.0f}%) — cost change looks price-driven, not usage-driven."
                ),
                "observed_excess": metrics["observed_excess"],
                "metrics": metrics,
            })

    # Rule 4: sustained condition — elevated usage for N+ consecutive months
    sustained = _check_sustained(conn, property_id, category, month, th)
    if sustained:
        anomalies.append(sustained)

    # Rule 5: missing occupancy or consumption for this property/month
    if metrics["occupied_units"] is None:
        anomalies.append({
            "rule": "missing_occupancy",
            "severity": "Low",
            "confidence": "Strong",
            "cause": "Billing",
            "message": f"{prop_name}: no occupancy data for {month} — per-unit metrics can't be normalized.",
            "observed_excess": None,
            "metrics": metrics,
        })

    # Rule 6: value more than N standard deviations above history
    stddev_flag = _check_stddev(conn, property_id, category, month, th)
    if stddev_flag:
        anomalies.append(stddev_flag)

    return anomalies


def _check_sustained(conn, property_id, category, month, th):
    """Usage per occupied unit above baseline for `sustained_months` consecutive months
    ending at `month`."""
    months = analysis.list_months_with_data(conn, property_id, category)
    if month not in months:
        return None
    idx = months.index(month)
    if idx + 1 < th["sustained_months"]:
        return None

    window = months[idx + 1 - th["sustained_months"]: idx + 1]
    all_elevated = True
    for m in window:
        metrics = analysis.compute_property_month_metrics(conn, property_id, category, m)
        if not metrics or metrics["usage_pct_over_baseline"] is None:
            all_elevated = False
            break
        if metrics["usage_pct_over_baseline"] <= th["usage_pct"]:
            all_elevated = False
            break

    if not all_elevated:
        return None

    prop = db_module.get_property(conn, property_id)
    prop_name = prop["name"] if prop else f"Property {property_id}"
    current_metrics = analysis.compute_property_month_metrics(conn, property_id, category, month)
    return {
        "rule": "sustained_elevated_usage",
        "severity": "High",
        "confidence": "Strong",
        "cause": "Usage",
        "message": (
            f"{prop_name} {category} usage per occupied unit has stayed above baseline "
            f"for {th['sustained_months']} or more consecutive months through {month} — "
            f"this looks like an ongoing condition, not a one-off."
        ),
        "observed_excess": current_metrics["observed_excess"] if current_metrics else None,
        "metrics": current_metrics,
    }


def _check_stddev(conn, property_id, category, month, th):
    invoices = analysis.get_property_invoices(conn, property_id, category)
    costs = [i["total_cost"] for i in invoices if i["month"] != month and i["total_cost"]]
    current = next((i for i in invoices if i["month"] == month), None)
    if len(costs) < 4 or not current:
        return None

    mean = statistics.mean(costs)
    stdev = statistics.pstdev(costs)
    if stdev == 0:
        return None

    z = (current["total_cost"] - mean) / stdev
    if z <= th["stddev"]:
        return None

    prop = db_module.get_property(conn, property_id)
    prop_name = prop["name"] if prop else f"Property {property_id}"
    metrics = analysis.compute_property_month_metrics(conn, property_id, category, month)
    return {
        "rule": "stddev_outlier",
        "severity": "High" if z > th["stddev"] * 1.5 else "Medium",
        "confidence": "Likely",
        "cause": metrics.get("cause", "Unknown") if metrics else "Unknown",
        "message": (
            f"{prop_name} {category} cost for {month} is {z:.1f} standard deviations "
            f"above its own history (threshold: {th['stddev']:.1f})."
        ),
        "observed_excess": metrics["observed_excess"] if metrics else None,
        "metrics": metrics,
    }


def scan_all(conn, only_latest_month=False, apply_dismissals=True, recent_months=3):
    """
    Runs anomaly checks across every property/category/month combination that
    has approved invoice data.

    only_latest_month: if True, checks the last `recent_months` months per
    property/category rather than full history — used by triage, which cares
    about current signals, not re-surfacing every historical month every time.
    A window rather than a single month matters: if the newest month has a
    data-quality gap (e.g. missing occupancy) with no cost signal of its own,
    checking only that one month would hide a real, still-ongoing incident
    from the month before it. Incident grouping combines whatever months are
    returned here into one incident, so the data-quality flag and the real
    issue end up merged rather than one masking the other.

    apply_dismissals: if True (default), skips any (property, category, rule)
    combination the user has previously dismissed via Settings/incidents.
    """
    results = []
    for prop in db_module.list_properties(conn):
        for category in ("Water", "Electricity", "Natural Gas", "Other"):
            months = analysis.list_months_with_data(conn, prop["id"], category)
            if only_latest_month:
                months = months[-recent_months:] if months else []
            for m in months:
                found = check_property_month(conn, prop["id"], category, m)
                for f in found:
                    if apply_dismissals and db_module.is_pattern_dismissed(
                        conn, prop["id"], category, f["rule"]
                    ):
                        continue
                    f["property_id"] = prop["id"]
                    f["property_name"] = prop["name"]
                    f["category"] = category
                    f["month"] = m
                    results.append(f)
    return results
