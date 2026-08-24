"""
services/settings_service.py
"""

from engine import db, extraction, reporting
from backend.schemas.overview import ThresholdSettings, DismissedPatternOut
from backend.schemas.properties import OccupancyImportRow


def get_thresholds() -> ThresholdSettings:
    conn = db.get_conn()
    try:
        s = db.get_all_settings(conn)
        return ThresholdSettings(
            threshold_yoy_pct=float(s.get("threshold_yoy_pct", 15)),
            threshold_usage_pct=float(s.get("threshold_usage_pct", 20)),
            threshold_rate_pct=float(s.get("threshold_rate_pct", 10)),
            threshold_sustained_months=int(s.get("threshold_sustained_months", 2)),
            threshold_stddev=float(s.get("threshold_stddev", 2)),
        )
    finally:
        conn.close()


def update_thresholds(payload: ThresholdSettings) -> ThresholdSettings:
    conn = db.get_conn()
    try:
        db.set_setting(conn, "threshold_yoy_pct", payload.threshold_yoy_pct)
        db.set_setting(conn, "threshold_usage_pct", payload.threshold_usage_pct)
        db.set_setting(conn, "threshold_rate_pct", payload.threshold_rate_pct)
        db.set_setting(conn, "threshold_sustained_months", payload.threshold_sustained_months)
        db.set_setting(conn, "threshold_stddev", payload.threshold_stddev)
        return payload
    finally:
        conn.close()


def list_dismissed_patterns() -> list[DismissedPatternOut]:
    conn = db.get_conn()
    try:
        return [DismissedPatternOut(**dict(p)) for p in db.list_dismissed_patterns(conn)]
    finally:
        conn.close()


def preview_occupancy_import(file_bytes: bytes, filename: str) -> list[OccupancyImportRow]:
    conn = db.get_conn()
    try:
        df = extraction.read_tabular_file(file_bytes, filename)
        df.columns = [c.strip().lower() for c in df.columns]
        properties = db.list_properties(conn)
        out = []
        for _, row in df.iterrows():
            prop_match = next(
                (p for p in properties if p["name"].lower() == str(row.get("property", "")).lower()), None
            )
            occupied = int(row.get("occupied_units", 0) or 0)
            vacant = int(row.get("vacant_units", 0) or 0)
            valid = prop_match is not None
            reason = None
            if not prop_match:
                reason = "Property name not found"
            elif prop_match["units"] and (occupied + vacant) > prop_match["units"]:
                valid = False
                reason = f"Occupied+vacant exceeds total units ({prop_match['units']})"
            out.append(OccupancyImportRow(
                property_name=str(row.get("property", "")), month=str(row.get("month", "")),
                occupied_units=occupied, vacant_units=vacant, valid=valid, reason=reason,
            ))
        return out
    finally:
        conn.close()


def commit_occupancy_import(file_bytes: bytes, filename: str) -> dict:
    conn = db.get_conn()
    try:
        df = extraction.read_tabular_file(file_bytes, filename)
        df.columns = [c.strip().lower() for c in df.columns]
        properties = db.list_properties(conn)
        imported, skipped = 0, 0
        for _, row in df.iterrows():
            prop_match = next(
                (p for p in properties if p["name"].lower() == str(row.get("property", "")).lower()), None
            )
            if not prop_match:
                skipped += 1
                continue
            occupied = int(row.get("occupied_units", 0) or 0)
            vacant = int(row.get("vacant_units", 0) or 0)
            if prop_match["units"] and (occupied + vacant) > prop_match["units"]:
                skipped += 1
                continue
            db.upsert_occupancy(conn, prop_match["id"], str(row.get("month", "")), occupied, vacant)
            imported += 1
        return {"imported": imported, "skipped": skipped}
    finally:
        conn.close()


def create_backup() -> str:
    dest = db.DATA_DIR / f"backup_{db.now_iso().replace(':', '-')}.db"
    db.backup_db(str(dest))
    return str(dest)


def export_csv_zip() -> bytes:
    return db.export_all_csv_zip()


def generate_report(fmt: str, month: str | None) -> tuple[bytes, str, str]:
    conn = db.get_conn()
    try:
        findings = db.list_findings(conn)
        if fmt == "md":
            content = reporting.generate_markdown(findings, month=month)
            return content.encode(), "text/markdown", "monthly_action_report.md"
        if fmt == "csv":
            content = reporting.generate_csv(findings, month=month)
            return content.encode(), "text/csv", "monthly_action_report.csv"
        if fmt == "pdf":
            content = reporting.generate_pdf(findings, month=month)
            return content, "application/pdf", "monthly_action_report.pdf"
        raise ValueError(f"Unknown format: {fmt}")
    finally:
        conn.close()
