"""
services/incidents_service.py
"""

from engine import db, incidents, analysis
from backend.schemas.incidents import (
    IncidentOut, FindingOut, ActionOut,
)


def _incident_to_out(inc: dict) -> IncidentOut:
    latest_metrics = None
    for a in inc["anomalies"]:
        if a["month"] == inc["latest_month"] and a.get("metrics"):
            latest_metrics = a["metrics"]
            break
    explanation = latest_metrics.get("explanation") if latest_metrics else None
    primary_invoice_id = latest_metrics.get("invoice_id") if latest_metrics else None

    return IncidentOut(
        property_id=inc["property_id"], property_name=inc["property_name"],
        category=inc["category"], months=inc["months"], latest_month=inc["latest_month"],
        rules=inc["rules"], severity=inc["severity"], confidence=inc["confidence"],
        cause=inc["cause"], tier=inc["tier"],
        observed_excess_monthly=inc["observed_excess_monthly"] or 0.0,
        annualized_impact=inc["annualized_impact"] or 0.0, score=inc["score"],
        messages=inc["messages"], is_data_quality_only=inc["is_data_quality_only"],
        explanation=explanation, primary_invoice_id=primary_invoice_id,
    )


def list_incidents(tier: str | None = None, property_id: int | None = None,
                    category: str | None = None) -> list[IncidentOut]:
    conn = db.get_conn()
    try:
        triaged = incidents.get_triaged_incidents(conn)
        out = []
        for inc in triaged:
            if tier and inc["tier"] != tier:
                continue
            if property_id and inc["property_id"] != property_id:
                continue
            if category and inc["category"] != category:
                continue
            out.append(_incident_to_out(inc))
        return out
    finally:
        conn.close()


def _find_incident(conn, property_id: int, category: str, rules: list[str]):
    all_incidents = incidents.get_triaged_incidents(conn)
    return next(
        (inc for inc in all_incidents if inc["property_id"] == property_id
         and inc["category"] == category and set(inc["rules"]) == set(rules)),
        None,
    )


def dismiss_incident(property_id: int, category: str, rules: list[str], reason: str) -> bool:
    conn = db.get_conn()
    try:
        inc = _find_incident(conn, property_id, category, rules)
        if not inc:
            return False
        incidents.dismiss_incident(conn, inc, reason=reason)
        return True
    finally:
        conn.close()


def confirm_incident(property_id: int, category: str, rules: list[str],
                      recommended_action: str | None, set_status: str) -> int | None:
    conn = db.get_conn()
    try:
        inc = _find_incident(conn, property_id, category, rules)
        if not inc:
            return None
        kwargs = {}
        if recommended_action:
            kwargs["recommended_action"] = recommended_action
        fid = incidents.create_finding_from_incident(conn, inc, **kwargs)
        db.update_finding_status(conn, fid, set_status)
        return fid
    finally:
        conn.close()


def list_dismissed_patterns():
    conn = db.get_conn()
    try:
        return [dict(p) for p in db.list_dismissed_patterns(conn)]
    finally:
        conn.close()


def remove_dismissed_pattern(pattern_id: int) -> bool:
    conn = db.get_conn()
    try:
        db.remove_dismissed_pattern(conn, pattern_id)
        return True
    finally:
        conn.close()


# ------------------------------------------------------------- findings ----

def list_findings(status: str | None = None) -> list[FindingOut]:
    conn = db.get_conn()
    try:
        rows = db.list_findings(conn, status=status)
        out = []
        for r in rows:
            d = dict(r)
            source_ids = [int(i) for i in d["source_invoice_ids"].split(",") if i] if d["source_invoice_ids"] else []
            out.append(FindingOut(
                id=d["id"], property_id=d["property_id"], property_name=d["property_name"],
                category=d["category"], description=d["description"], evidence=d["evidence"],
                observed_excess=d["observed_excess"], recommended_action=d["recommended_action"],
                severity=d["severity"], confidence=d["confidence"], cause=d["cause"],
                owner=d["owner"], status=d["status"], source_invoice_ids=source_ids,
                dismissed_reason=d["dismissed_reason"], created_at=d["created_at"],
            ))
        return out
    finally:
        conn.close()


def update_finding_status(finding_id: int, status: str, dismissed_reason: str | None) -> bool:
    conn = db.get_conn()
    try:
        db.update_finding_status(conn, finding_id, status, dismissed_reason=dismissed_reason)
        return True
    finally:
        conn.close()


# -------------------------------------------------------------- actions ----

def list_actions(finding_id: int | None = None) -> list[ActionOut]:
    conn = db.get_conn()
    try:
        rows = db.list_actions(conn, finding_id=finding_id)
        return [ActionOut(
            id=r["id"], finding_id=r["finding_id"], finding_description=r["finding_description"],
            property_id=r["property_id"], property_name=r["property_name"],
            action_taken=r["action_taken"], owner=r["owner"], due_date=r["due_date"],
            status=r["status"], notes=r["notes"], expected_savings=r["expected_savings"],
            confirmed_savings=r["confirmed_savings"], created_at=r["date"],
        ) for r in rows]
    finally:
        conn.close()


def create_action(finding_id: int, action_taken: str, owner: str, due_date: str,
                   expected_savings: float | None, notes: str) -> int:
    conn = db.get_conn()
    try:
        return db.insert_action(conn, finding_id, action_taken, owner=owner, due_date=due_date,
                                 expected_savings=expected_savings, notes=notes)
    finally:
        conn.close()


def get_action(action_id: int) -> ActionOut | None:
    conn = db.get_conn()
    try:
        r = db.get_action(conn, action_id)
        if not r:
            return None
        return ActionOut(
            id=r["id"], finding_id=r["finding_id"], finding_description=r["finding_description"],
            property_id=r["property_id"], property_name=r["property_name"],
            action_taken=r["action_taken"], owner=r["owner"], due_date=r["due_date"],
            status=r["status"], notes=r["notes"], expected_savings=r["expected_savings"],
            confirmed_savings=r["confirmed_savings"], created_at=r["date"],
        )
    finally:
        conn.close()


def update_action(action_id: int, status: str | None, notes: str | None,
                   confirmed_savings: float | None, owner: str | None, due_date: str | None) -> bool:
    conn = db.get_conn()
    try:
        db.update_action(conn, action_id, status=status, notes=notes,
                          confirmed_savings=confirmed_savings)
        if owner is not None or due_date is not None:
            fields = []
            params = []
            if owner is not None:
                fields.append("owner = ?")
                params.append(owner)
            if due_date is not None:
                fields.append("due_date = ?")
                params.append(due_date)
            params.append(action_id)
            conn.execute(f"UPDATE actions SET {', '.join(fields)} WHERE id = ?", params)
            conn.commit()
        return True
    finally:
        conn.close()
