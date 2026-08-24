"""
services/properties_service.py
"""

from engine import db, analysis, incidents
from backend.schemas.properties import (
    PropertyOut, PropertyCreate, CategoryMonthMetrics, TrendPoint,
    PropertyDetail, OccupancyOut,
)

CATEGORIES = ["Water", "Electricity", "Natural Gas", "Other"]


def list_properties() -> list[PropertyOut]:
    conn = db.get_conn()
    try:
        return [PropertyOut(**dict(p)) for p in db.list_properties(conn)]
    finally:
        conn.close()


def create_property(payload: PropertyCreate) -> PropertyOut:
    conn = db.get_conn()
    try:
        db.add_property(
            conn, payload.name, address=payload.address, units=payload.units,
            sqft=payload.sqft, construction_year=payload.construction_year,
            heating_type=payload.heating_type, metering_type=payload.metering_type,
        )
        row = next(p for p in db.list_properties(conn) if p["name"] == payload.name)
        return PropertyOut(**dict(row))
    finally:
        conn.close()


def get_property_detail(property_id: int) -> PropertyDetail | None:
    conn = db.get_conn()
    try:
        prop_row = db.get_property(conn, property_id)
        if not prop_row:
            return None

        current_rows = []
        for cat in CATEGORIES:
            months = analysis.list_months_with_data(conn, property_id, cat)
            if not months:
                continue
            metrics = analysis.compute_property_month_metrics(conn, property_id, cat, months[-1])
            if metrics:
                current_rows.append(CategoryMonthMetrics(
                    category=cat, month=months[-1], total_cost=metrics["total_cost"],
                    occupied_units=metrics["occupied_units"],
                    cost_per_occupied_unit=metrics["cost_per_occupied_unit"],
                    consumption_per_occupied_unit=metrics["consumption_per_occupied_unit"],
                    usage_per_unit_per_day=metrics["usage_per_unit_per_day"],
                    effective_rate=metrics["effective_rate"],
                    yoy_variance_pct=metrics["yoy_variance_pct"],
                    expected_cost=metrics["expected_cost"],
                    observed_excess=metrics["observed_excess"],
                    cause=metrics["cause"],
                    baseline_method=metrics["baseline_method"],
                    baseline_confidence=metrics["baseline_confidence"],
                    explanation=metrics["explanation"],
                ))

        all_incidents = incidents.get_triaged_incidents(conn)
        open_count = sum(1 for inc in all_incidents if inc["property_id"] == property_id)

        return PropertyDetail(
            property=PropertyOut(**dict(prop_row)),
            current_month_by_category=current_rows,
            open_incident_count=open_count,
        )
    finally:
        conn.close()


def get_property_trend(property_id: int, category: str, months_back: int = 12) -> list[TrendPoint]:
    conn = db.get_conn()
    try:
        months = analysis.list_months_with_data(conn, property_id, category)
        out = []
        for m in months[-months_back:]:
            metrics = analysis.compute_property_month_metrics(conn, property_id, category, m)
            if metrics:
                out.append(TrendPoint(
                    month=m, total_cost=metrics["total_cost"],
                    expected_cost=metrics["expected_cost"], invoice_id=metrics["invoice_id"],
                ))
        return out
    finally:
        conn.close()


def get_property_category_metrics(property_id: int, category: str, month: str) -> CategoryMonthMetrics | None:
    conn = db.get_conn()
    try:
        metrics = analysis.compute_property_month_metrics(conn, property_id, category, month)
        if not metrics:
            return None
        return CategoryMonthMetrics(
            category=category, month=month, total_cost=metrics["total_cost"],
            occupied_units=metrics["occupied_units"],
            cost_per_occupied_unit=metrics["cost_per_occupied_unit"],
            consumption_per_occupied_unit=metrics["consumption_per_occupied_unit"],
            usage_per_unit_per_day=metrics["usage_per_unit_per_day"],
            effective_rate=metrics["effective_rate"],
            yoy_variance_pct=metrics["yoy_variance_pct"],
            expected_cost=metrics["expected_cost"],
            observed_excess=metrics["observed_excess"],
            cause=metrics["cause"],
            baseline_method=metrics["baseline_method"],
            baseline_confidence=metrics["baseline_confidence"],
            explanation=metrics["explanation"],
        )
    finally:
        conn.close()


def list_property_months(property_id: int, category: str) -> list[str]:
    conn = db.get_conn()
    try:
        return analysis.list_months_with_data(conn, property_id, category)
    finally:
        conn.close()


def list_occupancy(property_id: int | None = None) -> list[OccupancyOut]:
    conn = db.get_conn()
    try:
        rows = db.list_occupancy(conn, property_id=property_id)
        return [OccupancyOut(**dict(r)) for r in rows]
    finally:
        conn.close()


def upsert_occupancy(property_id: int, month: str, occupied_units: int, vacant_units: int) -> dict:
    conn = db.get_conn()
    try:
        prop = db.get_property(conn, property_id)
        if not prop:
            return {"ok": False, "message": "Property not found"}
        if prop["units"] and (occupied_units + vacant_units) > prop["units"]:
            return {"ok": False, "message": f"Occupied + vacant ({occupied_units + vacant_units}) exceeds total units ({prop['units']})"}
        db.upsert_occupancy(conn, property_id, month, occupied_units, vacant_units)
        return {"ok": True}
    finally:
        conn.close()
