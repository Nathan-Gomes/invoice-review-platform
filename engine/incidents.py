"""
incidents.py - Anomaly Triage. Draft 2 surfaced one row per rule per month
(133 anomalies from 365 invoices). This groups related signals into one
incident per (property, category, contiguous run of anomalous months), ranks
incidents by financial impact/severity/confidence, and classifies each into
Critical / Watch / Informational so an operator can scan five things instead
of a hundred and thirty-three.
"""

from collections import defaultdict

from engine import db as db_module
from engine import anomalies as anomalies_module

SEVERITY_WEIGHT = {"Low": 1, "Medium": 2, "High": 3}
CONFIDENCE_WEIGHT = {"Possible": 1, "Likely": 2, "Strong": 3}

COST_RULES = {
    "yoy_cost_increase", "usage_above_baseline", "rate_above_baseline",
    "sustained_elevated_usage", "stddev_outlier",
}


def _severity_rank(s):
    return SEVERITY_WEIGHT.get(s, 0)


def _confidence_rank(c):
    return CONFIDENCE_WEIGHT.get(c, 0)


def group_into_incidents(conn, raw_anomalies):
    """
    Groups raw per-rule, per-month anomalies into one incident per
    (property, category), combining every rule that fired for that
    property/category across all flagged months in this scan into a single
    reviewable item, instead of a separate row for each rule and each month.
    """
    groups = defaultdict(list)
    for a in raw_anomalies:
        key = (a["property_id"], a["category"])
        groups[key].append(a)

    incidents = []
    for (property_id, category), anomaly_list in groups.items():
        months = sorted({a["month"] for a in anomaly_list})
        rules = sorted({a["rule"] for a in anomaly_list})
        max_severity = max(anomaly_list, key=lambda a: _severity_rank(a["severity"]))["severity"]
        max_confidence = max(anomaly_list, key=lambda a: _confidence_rank(a["confidence"]))["confidence"]

        causes = {a["cause"] for a in anomaly_list if a.get("cause") and a["cause"] != "Unknown"}
        cause = sorted(causes)[0] if len(causes) == 1 else ("Mixed" if len(causes) > 1 else "Unknown")

        latest_month = months[-1]
        # Use the most recent month that actually has a dollar figure — the
        # literal latest month might be a data-quality-only month (e.g.
        # missing_occupancy) with no cost signal of its own, and picking that
        # month's observed_excess would zero out the impact of a real,
        # still-active issue from a month just before it.
        months_with_excess = sorted(
            {a["month"] for a in anomaly_list if a.get("observed_excess") is not None},
            reverse=True,
        )
        impact_month = months_with_excess[0] if months_with_excess else None
        latest_anomaly = next(
            (a for a in anomaly_list if a["month"] == impact_month and a.get("observed_excess") is not None),
            None,
        ) if impact_month else None
        observed_excess_monthly = latest_anomaly["observed_excess"] if latest_anomaly else 0.0
        annualized_impact = (observed_excess_monthly or 0.0) * 12

        property_name = anomaly_list[0]["property_name"]
        messages = [a["message"] for a in anomaly_list if a["month"] == latest_month]

        is_data_quality_only = rules == ["missing_occupancy"]

        incident = {
            "property_id": property_id,
            "property_name": property_name,
            "category": category,
            "months": months,
            "latest_month": latest_month,
            "rules": rules,
            "severity": max_severity,
            "confidence": max_confidence,
            "cause": cause,
            "observed_excess_monthly": observed_excess_monthly,
            "annualized_impact": annualized_impact,
            "messages": messages,
            "is_data_quality_only": is_data_quality_only,
            "anomalies": anomaly_list,
        }
        incident["tier"] = classify_tier(incident)
        incident["score"] = _score(incident)
        incidents.append(incident)

    incidents.sort(key=lambda i: i["score"], reverse=True)
    return incidents


def classify_tier(incident):
    """
    Critical: high-confidence, meaningful dollar impact, or high severity with
      likely-or-better confidence.
    Watch: real signal but lower confidence or smaller impact.
    Informational: data-quality issues (e.g. missing occupancy) with no cost
      signal.
    """
    if incident["is_data_quality_only"]:
        return "Informational"

    sev = incident["severity"]
    conf = incident["confidence"]
    impact = incident["annualized_impact"] or 0

    if conf == "Strong" and sev in ("High", "Medium") and impact >= 300:
        return "Critical"
    if sev == "High" and conf in ("Likely", "Strong"):
        return "Critical"
    if impact >= 1500 and conf in ("Likely", "Strong"):
        return "Critical"

    if sev in ("Medium", "High") or conf in ("Likely", "Strong") or impact >= 200:
        return "Watch"

    return "Informational"


def _score(incident):
    """Ranking score: financial impact dominates, with severity/confidence
    as tiebreakers so two incidents with similar dollars still rank the
    more certain one higher."""
    impact = incident["annualized_impact"] or 0
    severity_component = _severity_rank(incident["severity"]) * 50
    confidence_component = _confidence_rank(incident["confidence"]) * 25
    return impact + severity_component + confidence_component


def get_triaged_incidents(conn, only_latest_month=True):
    """Convenience wrapper: scan, group, and rank in one call."""
    raw = anomalies_module.scan_all(conn, only_latest_month=only_latest_month)
    return group_into_incidents(conn, raw)


def dismiss_incident(conn, incident, reason=""):
    """Dismissing an incident remembers every rule involved for this
    property+category, so the same combination of signals doesn't resurface
    on the next scan. A genuinely new rule (not part of this incident) will
    still fire normally."""
    for rule in incident["rules"]:
        db_module.dismiss_pattern(conn, incident["property_id"], incident["category"], rule, reason=reason)


def create_finding_from_incident(conn, incident, recommended_action=None):
    """Promotes a triaged incident into a persisted Finding, built from the
    grouped incident rather than a single raw rule hit."""
    evidence = " | ".join(incident["messages"]) if incident["messages"] else "; ".join(incident["rules"])
    source_ids = sorted({
        a["metrics"]["invoice_id"] for a in incident["anomalies"]
        if a.get("metrics") and a["metrics"].get("invoice_id")
    })
    description = (
        f"{incident['property_name']} {incident['category']}: "
        f"{', '.join(r.replace('_', ' ') for r in incident['rules'])}"
    )
    return db_module.insert_finding(
        conn,
        property_id=incident["property_id"],
        category=incident["category"],
        description=description,
        evidence=evidence,
        observed_excess=incident["annualized_impact"],
        recommended_action=recommended_action or "Investigate cause and confirm whether action is needed.",
        severity=incident["severity"],
        confidence=incident["confidence"],
        cause=incident["cause"],
        source_invoice_ids=source_ids,
    )
