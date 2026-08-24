"""
analysis.py — Property-month analysis: normalized metrics, trailing baselines,
and the expected-cost / observed-excess calculation used by both the Analysis
screen and the anomaly rules.

Everything here operates on already-approved invoices only — draft/pending
invoices never enter analysis (that's the whole point of the Review gate).
"""

import statistics
from datetime import date
from dateutil.relativedelta import relativedelta

from engine import db as db_module
from engine import units


def _canonical_consumption(category, consumption, consumption_unit):
    """
    Converts gas consumption to therms (the one canonical unit used for any
    cross-invoice comparison) — see engine/units.py. Water and electricity
    pass through unchanged. This must be applied consistently to both the
    baseline invoices AND the current month's invoice before any
    percent-over-baseline comparison, or a property whose gas invoices
    happen to arrive in different units (CCF one period, m3 another) would
    get a meaningless "usage change" purely from the unit mismatch.
    """
    if category != "Natural Gas":
        return consumption
    return units.normalize_gas_consumption(consumption, consumption_unit)


def _month_str(d: date) -> str:
    return d.strftime("%Y-%m")


def _parse_month(m: str) -> date:
    return date(int(m[:4]), int(m[5:7]), 1)


def get_property_invoices(conn, property_id, category):
    """Approved invoices for one property+category, with a normalized 'month' key
    (the billing_start's month) attached."""
    rows = db_module.list_approved_invoices(conn, property_id=property_id, category=category)
    out = []
    for r in rows:
        d = dict(r)
        if d.get("billing_start"):
            try:
                d["month"] = d["billing_start"][:7]
            except Exception:
                d["month"] = None
        else:
            d["month"] = None
        out.append(d)
    return out


def get_occupied_units(conn, property_id, month):
    occ = db_module.get_occupancy(conn, property_id, month)
    return occ["occupied_units"] if occ else None


def billing_days(invoice: dict) -> int:
    if not invoice.get("billing_start") or not invoice.get("billing_end"):
        return None
    try:
        start = date.fromisoformat(invoice["billing_start"])
        end = date.fromisoformat(invoice["billing_end"])
        return max((end - start).days, 1)
    except ValueError:
        return None


def _default_buffer_months(conn):
    """
    How many recent months to exclude from the baseline window, on top of
    excluding the target month itself. Defaults to the 'sustained' threshold:
    if a condition can persist for that many months before being flagged,
    the baseline needs to look further back than that or it starts averaging
    in the very anomaly it's meant to detect.
    """
    val = db_module.get_setting(conn, "threshold_sustained_months", "2")
    try:
        return int(val)
    except (TypeError, ValueError):
        return 2


def compute_baseline(conn, property_id, category, before_month,
                      trailing_months=12, buffer_months=None):
    """
    Season-aware baseline: prefers comparing against the same calendar month
    in prior years (so a January bill is judged against prior Januaries, not
    against a trailing average that mixes in shoulder-season months). Falls
    back to a buffered trailing window (see the trailing_window branch below)
    only when there isn't enough same-season history yet.

    Usage is normalized per occupied unit *per billing day*, since invoices
    for the same property can span anywhere from 28 to 36+ days — comparing
    raw per-unit consumption across periods of different length overstates
    or understates real change.

    Returns a dict: usage_per_unit_per_day, rate, method, sample_size, confidence.
    confidence is one of "Insufficient", "Low", "Moderate", "High" — callers
    should not present a finding as settled when confidence is "Insufficient".
    """
    if buffer_months is None:
        buffer_months = _default_buffer_months(conn)

    invoices = get_property_invoices(conn, property_id, category)
    target = _parse_month(before_month)

    def _per_day_usage_and_rate(inv):
        days = billing_days(inv) or 30
        occ = get_occupied_units(conn, property_id, inv["month"])
        raw_consumption = inv.get("consumption")
        canonical_consumption = _canonical_consumption(category, raw_consumption, inv.get("consumption_unit"))
        usage_pd = (canonical_consumption / occ / days) if (occ and canonical_consumption) else None
        rate = (inv["total_cost"] / canonical_consumption) if canonical_consumption else None
        return usage_pd, rate

    # Prefer same calendar month across prior years ("same season").
    season_usage, season_rate = [], []
    for inv in invoices:
        if not inv["month"]:
            continue
        m = _parse_month(inv["month"])
        if m.month == target.month and m < target:
            u, r = _per_day_usage_and_rate(inv)
            if u is not None:
                season_usage.append(u)
            if r is not None:
                season_rate.append(r)

    if len(season_usage) >= 2:
        method = "same_season_yoy"
        sample_size = len(season_usage)
        usage_per_day = statistics.mean(season_usage)
        rate = statistics.mean(season_rate) if season_rate else None
    else:
        window_end = target - relativedelta(months=buffer_months)
        window_start = window_end - relativedelta(months=trailing_months)
        trailing_usage, trailing_rate = [], []
        for inv in invoices:
            if not inv["month"]:
                continue
            m = _parse_month(inv["month"])
            if window_start <= m < window_end:
                u, r = _per_day_usage_and_rate(inv)
                if u is not None:
                    trailing_usage.append(u)
                if r is not None:
                    trailing_rate.append(r)
        method = "trailing_window" if trailing_usage else None
        sample_size = len(trailing_usage)
        usage_per_day = statistics.mean(trailing_usage) if trailing_usage else None
        rate = statistics.mean(trailing_rate) if trailing_rate else None

    confidence = _baseline_confidence(sample_size, method)
    return {
        "usage_per_unit_per_day": usage_per_day,
        "rate": rate,
        "method": method,
        "sample_size": sample_size,
        "confidence": confidence,
    }


def _baseline_confidence(sample_size, method):
    """
    Same-season comparisons can reach 'High' confidence with fewer points,
    since they're already adjusted for seasonality. A trailing window is
    never season-adjusted, so it's capped at 'Moderate' even with lots of
    history — that cap is what "require enough history before high-confidence
    alerts" means in practice here.
    """
    if not sample_size:
        return "Insufficient"
    if method == "same_season_yoy":
        if sample_size >= 4:
            return "High"
        if sample_size >= 2:
            return "Moderate"
        return "Low"
    # trailing_window
    if sample_size >= 9:
        return "Moderate"
    if sample_size >= 3:
        return "Low"
    return "Insufficient"


def classify_cause(conn, metrics, baseline):
    """
    Distinguishes usage increases from rate increases from occupancy/billing
    data problems, using the same thresholds as the anomaly rules so the
    "cause" shown to a user always matches the rule that would fire.
    """
    th = db_module.get_thresholds(conn)

    if metrics.get("occupied_units") is None:
        return "Occupancy"

    usage_pct = metrics.get("usage_pct_over_baseline")
    rate_pct = metrics.get("rate_pct_over_baseline")
    usage_flag = usage_pct is not None and usage_pct > th["usage_pct"]
    rate_flag = rate_pct is not None and rate_pct > th["rate_pct"]

    if usage_flag and not rate_flag:
        return "Usage"
    if rate_flag and not usage_flag:
        return "Rate"
    if usage_flag and rate_flag:
        return "Usage" if usage_pct >= rate_pct else "Rate"
    return "Unknown"


def explain_metrics(metrics, baseline, property_name, category):
    """Plain-language explanation, in the same spirit as: 'Water cost increased
    24%, but the municipal rate increased only 4%. After adjusting for billing
    days and occupancy, consumption per occupied unit increased 18%...'"""
    parts = []

    if metrics.get("yoy_variance_pct") is not None:
        parts.append(
            f"{property_name} {category} cost is {metrics['yoy_variance_pct']:+.0f}% "
            f"vs. the same month last year"
        )

    if baseline.get("confidence") == "Insufficient":
        parts.append("but there isn't enough history yet for a confident baseline")
        return ". ".join(p.capitalize() if i == 0 else p for i, p in enumerate(parts)) + "."

    usage_pct = metrics.get("usage_pct_over_baseline")
    rate_pct = metrics.get("rate_pct_over_baseline")
    if usage_pct is not None:
        basis = "same-season" if baseline.get("method") == "same_season_yoy" else "trailing"
        parts.append(
            f"after adjusting for occupancy and billing days, usage per occupied unit "
            f"is {usage_pct:+.0f}% vs. its {basis} baseline"
        )
    if rate_pct is not None and abs(rate_pct) > 1:
        parts.append(f"the effective rate is {rate_pct:+.0f}% vs. baseline")

    cause = metrics.get("cause")
    cause_text = {
        "Usage": "this looks usage-driven, not a rate change",
        "Rate": "this looks price-driven — usage itself is in line with baseline",
        "Occupancy": "occupancy data is missing, so this can't be normalized yet",
        "Unknown": "the cause isn't clear from the data alone yet",
    }.get(cause)
    if cause_text:
        parts.append(cause_text)

    if metrics.get("observed_excess"):
        parts.append(f"estimated excess for this period is ${metrics['observed_excess']:,.0f}")

    if baseline.get("confidence") == "Low":
        parts.append("confidence is still low — only a little comparable history exists")

    if not parts:
        return f"{property_name} {category}: nothing notable to explain for this period."

    sentence = "; ".join(parts) + "."
    return sentence[0].upper() + sentence[1:]


def compute_property_month_metrics(conn, property_id, category, month):
    """
    Core metrics for one property/category/month:
    total cost, cost per occupied unit, consumption per occupied unit,
    effective rate, YoY variance, expected cost, observed excess.

    One authoritative baseline (compute_baseline()) drives everything:
    the anomaly-rule triggers in anomalies.py, the cause classification,
    the plain-language explanation, and the dollar-denominated
    expected_cost/observed_excess below. Previously expected_cost used a
    separate, simpler trailing-only baseline that wasn't billing-day- or
    season-adjusted, which meant the estimated dollar impact didn't always
    agree with the reasoning stated in the explanation. That's fixed here:

    Expected cost = baseline usage-per-occupied-unit-per-day
                     x current occupied units x current billing days
                     x baseline effective rate.
    Observed excess = actual cost - expected cost.

    Returns None if there's no approved invoice for that property/category/month.
    """
    invoices = get_property_invoices(conn, property_id, category)
    current = next((i for i in invoices if i["month"] == month), None)
    if not current:
        return None

    occupied = get_occupied_units(conn, property_id, month)
    total_cost = current["total_cost"] or 0.0
    consumption = current.get("consumption")
    canonical_consumption = _canonical_consumption(category, consumption, current.get("consumption_unit"))
    days = billing_days(current)

    cost_per_occupied_unit = (total_cost / occupied) if occupied else None
    # consumption_per_occupied_unit stays in the invoice's own recorded unit
    # (matches what's shown alongside consumption_unit elsewhere). The two
    # ratios below feed into percent-over-baseline comparisons, so they must
    # use the SAME canonical unit the baseline was computed in — otherwise a
    # property billed in CCF one month and therms the next would show a
    # "usage change" that's really just a unit mismatch.
    consumption_per_occupied_unit = (consumption / occupied) if (occupied and consumption) else None
    effective_rate = (total_cost / canonical_consumption) if canonical_consumption else None
    usage_per_unit_per_day = (
        (canonical_consumption / occupied / days) if (occupied and canonical_consumption and days) else None
    )

    # Same-month-last-year comparison (unaffected by the baseline unification —
    # this is a direct actual-vs-actual comparison, not baseline-derived)
    target = _parse_month(month)
    last_year_month = _month_str(target - relativedelta(years=1))
    last_year_invoice = next((i for i in invoices if i["month"] == last_year_month), None)
    yoy_variance_pct = None
    if last_year_invoice and last_year_invoice["total_cost"]:
        yoy_variance_pct = (
            (total_cost - last_year_invoice["total_cost"]) / last_year_invoice["total_cost"] * 100
        )

    # The one authoritative baseline — season-aware where enough history
    # exists, billing-day-normalized, confidence-rated.
    baseline = compute_baseline(conn, property_id, category, month)

    usage_pct_over_baseline = None
    if usage_per_unit_per_day is not None and baseline.get("usage_per_unit_per_day"):
        usage_pct_over_baseline = (
            (usage_per_unit_per_day - baseline["usage_per_unit_per_day"])
            / baseline["usage_per_unit_per_day"] * 100
        )
    rate_pct_over_baseline = None
    if effective_rate is not None and baseline.get("rate"):
        rate_pct_over_baseline = (effective_rate - baseline["rate"]) / baseline["rate"] * 100

    expected_cost = None
    observed_excess = None
    if (
        baseline.get("usage_per_unit_per_day") is not None
        and baseline.get("rate") is not None
        and occupied is not None
        and days is not None
    ):
        expected_cost = baseline["usage_per_unit_per_day"] * occupied * days * baseline["rate"]
        observed_excess = total_cost - expected_cost

    result = {
        "property_id": property_id,
        "category": category,
        "month": month,
        "total_cost": total_cost,
        "occupied_units": occupied,
        "cost_per_occupied_unit": cost_per_occupied_unit,
        "consumption_per_occupied_unit": consumption_per_occupied_unit,
        "effective_rate": effective_rate,
        "yoy_variance_pct": yoy_variance_pct,
        "expected_cost": expected_cost,
        "observed_excess": observed_excess,
        "invoice_id": current["id"],
        "source_file_id": current["source_file_id"],
        "billing_days": days,
        "usage_per_unit_per_day": usage_per_unit_per_day,
        "usage_pct_over_baseline": usage_pct_over_baseline,
        "rate_pct_over_baseline": rate_pct_over_baseline,
        "baseline_method": baseline.get("method"),
        "baseline_sample_size": baseline.get("sample_size"),
        "baseline_confidence": baseline.get("confidence"),
    }
    result["cause"] = classify_cause(conn, result, baseline)
    prop = db_module.get_property(conn, property_id)
    prop_name = prop["name"] if prop else f"Property {property_id}"
    result["explanation"] = explain_metrics(result, baseline, prop_name, category)
    return result


def list_months_with_data(conn, property_id, category):
    invoices = get_property_invoices(conn, property_id, category)
    return sorted({i["month"] for i in invoices if i["month"]})
