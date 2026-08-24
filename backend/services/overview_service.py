"""
services/overview_service.py — aggregates data across properties/categories
into the single payload the Overview screen needs, so the frontend makes
one request instead of assembling it from several endpoints.
"""

from engine import db, analysis, incidents
from backend.schemas.overview import (
    OverviewResponse, OverviewMetrics, NeedsAttentionRow, PortfolioTrendPoint,
    CategoryBreakdown, PropertyRanking, RecentAction,
)

CATEGORIES = ["Water", "Electricity", "Natural Gas", "Other"]


def get_overview() -> OverviewResponse:
    conn = db.get_conn()
    try:
        properties = db.list_properties(conn)
        files = db.list_source_files(conn)
        needs_review = [f for f in files if f["filetype"] == "pdf" and f["status"] == "pending_review"]

        triaged = incidents.get_triaged_incidents(conn)
        critical = [i for i in triaged if i["tier"] == "Critical"]
        watch = [i for i in triaged if i["tier"] == "Watch"]
        total_excess = sum((i["annualized_impact"] or 0) for i in triaged)

        rows = []
        for p in properties:
            for cat in CATEGORIES:
                months = analysis.list_months_with_data(conn, p["id"], cat)
                if not months:
                    continue
                metrics = analysis.compute_property_month_metrics(conn, p["id"], cat, months[-1])
                if metrics:
                    rows.append({
                        "property_id": p["id"], "property_name": p["name"], "category": cat,
                        "month": months[-1], "total_cost": metrics["total_cost"],
                        "yoy_variance_pct": metrics["yoy_variance_pct"],
                        "observed_excess": metrics["observed_excess"],
                    })

        total_monthly_spend = sum(r["total_cost"] for r in rows)
        yoy_values = [r["yoy_variance_pct"] for r in rows if r["yoy_variance_pct"] is not None]
        avg_yoy = sum(yoy_values) / len(yoy_values) if yoy_values else None

        metrics_out = OverviewMetrics(
            total_monthly_spend=total_monthly_spend, yoy_variance_pct=avg_yoy,
            estimated_annual_excess=total_excess, invoices_needing_review=len(needs_review),
            open_critical_incidents=len(critical), open_watch_incidents=len(watch),
        )

        needs_attention = [
            NeedsAttentionRow(
                property_id=inc["property_id"], property_name=inc["property_name"],
                category=inc["category"], tier=inc["tier"], severity=inc["severity"],
                confidence=inc["confidence"], issue=inc["messages"][0] if inc["messages"] else "",
                cause=inc["cause"], annualized_impact=inc["annualized_impact"] or 0.0,
                latest_month=inc["latest_month"],
            )
            for inc in triaged[:10]
        ]

        # Portfolio trend: sum of total_cost by month across all properties/categories
        month_totals: dict[str, float] = {}
        for p in properties:
            for cat in CATEGORIES:
                months = analysis.list_months_with_data(conn, p["id"], cat)
                for m in months[-12:]:
                    met = analysis.compute_property_month_metrics(conn, p["id"], cat, m)
                    if met:
                        month_totals[m] = month_totals.get(m, 0.0) + met["total_cost"]
        portfolio_trend = [
            PortfolioTrendPoint(month=m, total_cost=month_totals[m]) for m in sorted(month_totals.keys())
        ]

        category_totals: dict[str, float] = {}
        for r in rows:
            category_totals[r["category"]] = category_totals.get(r["category"], 0.0) + r["total_cost"]
        category_breakdown = [
            CategoryBreakdown(category=c, total_cost=t) for c, t in
            sorted(category_totals.items(), key=lambda x: -x[1])
        ]

        by_property: dict[int, float] = {}
        prop_names = {p["id"]: p["name"] for p in properties}
        for r in rows:
            by_property[r["property_id"]] = by_property.get(r["property_id"], 0.0) + (r["observed_excess"] or 0.0)
        top_properties = [
            PropertyRanking(property_id=pid, property_name=prop_names.get(pid, "?"), observed_excess=excess)
            for pid, excess in sorted(by_property.items(), key=lambda x: -x[1])[:5]
        ]

        actions = db.list_actions(conn)
        recent_actions = [
            RecentAction(id=a["id"], property_name=a["property_name"], action_taken=a["action_taken"],
                         owner=a["owner"], status=a["status"], due_date=a["due_date"])
            for a in actions[:5]
        ]

        return OverviewResponse(
            metrics=metrics_out, needs_attention=needs_attention, portfolio_trend=portfolio_trend,
            category_breakdown=category_breakdown, top_properties_by_excess=top_properties,
            recent_actions=recent_actions,
        )
    finally:
        conn.close()
