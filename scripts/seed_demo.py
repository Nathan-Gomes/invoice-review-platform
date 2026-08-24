#!/usr/bin/env python3
"""Populate the demo database with a realistic, deterministic test portfolio."""

from __future__ import annotations

import argparse
import calendar
import hashlib
import io
import json
import math
import random
import shutil
import sys
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine import db, validation  # noqa: E402


SEED_START = date(2023, 7, 1)
SEED_END = date(2026, 7, 1)
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"

PROPERTIES = [
    {
        "name": "Cedar Place",
        "address": "118 Cedar Avenue, Toronto, ON",
        "units": 40,
        "sqft": 38200,
        "construction_year": 1974,
        "heating_type": "Natural gas boiler",
        "metering_type": "Bulk metered",
    },
    {
        "name": "Riverside Towers",
        "address": "825 Riverside Drive, Toronto, ON",
        "units": 72,
        "sqft": 68400,
        "construction_year": 1982,
        "heating_type": "Natural gas boiler",
        "metering_type": "Bulk metered",
    },
    {
        "name": "Harbour View",
        "address": "44 Harbour Street, Toronto, ON",
        "units": 58,
        "sqft": 55700,
        "construction_year": 1991,
        "heating_type": "Natural gas fan coil",
        "metering_type": "Bulk metered",
    },
    {
        "name": "Park Lane",
        "address": "301 Park Lane, Toronto, ON",
        "units": 32,
        "sqft": 30600,
        "construction_year": 1968,
        "heating_type": "Electric baseboard",
        "metering_type": "Mixed metering",
    },
    {
        "name": "Maple Court",
        "address": "67 Maple Court, Toronto, ON",
        "units": 24,
        "sqft": 23100,
        "construction_year": 2004,
        "heating_type": "Natural gas furnace",
        "metering_type": "Bulk metered",
    },
]

UTILITY_CONFIG = {
    "Water": {
        "vendor": "Toronto Water",
        "unit": "m3",
        "base_usage_per_unit": 9.5,
        "base_rate": 4.35,
        "prefix": "TW",
    },
    "Electricity": {
        "vendor": "Toronto Hydro",
        "unit": "kWh",
        "base_usage_per_unit": 410.0,
        "base_rate": 0.165,
        "prefix": "TH",
    },
    "Natural Gas": {
        "vendor": "Enbridge Gas",
        "unit": "m3",
        "base_usage_per_unit": 48.0,
        "base_rate": 0.49,
        "prefix": "EG",
    },
}


def month_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += relativedelta(months=1)


def seasonal_factor(category: str, month: int) -> float:
    if category == "Water":
        return {6: 1.08, 7: 1.15, 8: 1.12}.get(month, 0.98 if month in (1, 2) else 1.0)
    if category == "Electricity":
        return {6: 1.10, 7: 1.22, 8: 1.20, 12: 1.08, 1: 1.10}.get(month, 1.0)
    return {
        1: 2.35, 2: 2.15, 3: 1.65, 4: 1.05, 5: 0.62, 6: 0.42,
        7: 0.36, 8: 0.38, 9: 0.55, 10: 0.92, 11: 1.45, 12: 2.10,
    }[month]


def make_pdf_bytes(property_name: str, category: str, vendor: str, invoice_number: str,
                   billing_start: str, billing_end: str, consumption: float,
                   consumption_unit: str, taxes_fees: float, total_cost: float) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER, pageCompression=1)
    pdf.setTitle(f"{vendor} {invoice_number}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(54, 738, vendor)
    pdf.setFont("Helvetica", 10)
    lines = [
        ("Invoice number", invoice_number),
        ("Service address", property_name),
        ("Billing period", f"{billing_start} to {billing_end}"),
        ("Consumption", f"{consumption:,.1f} {consumption_unit}"),
        ("Taxes and fees", f"${taxes_fees:,.2f}"),
        ("Total amount due", f"${total_cost:,.2f}"),
        ("Category", category),
    ]
    y = 690
    for label, value in lines:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(54, y, f"{label}:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(175, y, value)
        y -= 28
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(54, 430, "Synthetic demonstration invoice - not a real bill")
    pdf.save()
    return buffer.getvalue()


def raw_invoice_text(fields: dict) -> str:
    return "\n".join([
        fields["vendor"],
        f"Invoice number: {fields['invoice_number']}",
        f"Service period: {fields['billing_start']} to {fields['billing_end']}",
        f"Consumption: {fields.get('consumption') or 0:,.1f} {fields.get('consumption_unit', '')}",
        f"Taxes: ${fields.get('taxes_fees') or 0:,.2f}",
        f"Total amount due: ${fields.get('total_cost') or 0:,.2f}",
    ])


def write_source_pdf(fields: dict, filename: str) -> tuple[Path, bytes]:
    pdf_bytes = make_pdf_bytes(
        fields.get("property_name") or "Unassigned property",
        fields.get("category") or "Unclassified",
        fields.get("vendor") or "Unknown vendor",
        fields.get("invoice_number") or "Needs review",
        fields.get("billing_start") or "Unknown",
        fields.get("billing_end") or "Unknown",
        fields.get("consumption") or 0,
        fields.get("consumption_unit") or "units",
        fields.get("taxes_fees") or 0,
        fields.get("total_cost") or 0,
    )
    path = UPLOAD_DIR / filename
    path.write_bytes(pdf_bytes)
    return path, pdf_bytes


def add_invoice(conn, fields: dict, filename: str, approved: bool,
                confidence: dict | None = None, logical_duplicate_of: int | None = None) -> int:
    path, pdf_bytes = write_source_pdf(fields, filename)
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    source_id = db.insert_source_file(
        conn, filename, file_hash, "pdf", str(path), raw_invoice_text(fields)
    )
    invoice_id = db.insert_draft_invoice(conn, source_id, fields, confidence or {})
    errors = validation.validate_invoice(fields)
    conn.execute(
        """UPDATE invoices
           SET validation_errors = ?, logical_duplicate_of = ?, last_modified_by = ?
           WHERE id = ?""",
        ("|".join(errors), logical_duplicate_of, "Demo Seeder", invoice_id),
    )
    conn.commit()
    if approved:
        db.approve_invoice(conn, invoice_id, source_id, approved_by="Demo Seeder")
    return invoice_id


def reset_demo_database() -> None:
    if db.ENV != "demo":
        raise SystemExit("Refusing to reset a non-demo environment.")
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    db.init_db()


def seed(reset: bool) -> dict:
    if db.ENV != "demo":
        raise SystemExit("Sample data may only be added to INVOICE_APP_ENV=demo.")

    db.init_db()
    conn = db.get_conn()
    existing = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    conn.close()
    if existing and not reset:
        raise SystemExit(
            f"Demo database already contains {existing} invoices. Run with --reset to replace demo data."
        )
    if reset:
        reset_demo_database()

    rng = random.Random(20260823)
    conn = db.get_conn()
    for prop in PROPERTIES:
        db.add_property(conn, **prop)
    property_rows = {row["name"]: row for row in db.list_properties(conn)}

    invoice_ids: dict[tuple[str, str, str], int] = {}
    approved_count = 0
    for prop_index, prop in enumerate(PROPERTIES):
        pid = property_rows[prop["name"]]["id"]
        for month_date in month_range(SEED_START, SEED_END):
            month = month_date.strftime("%Y-%m")
            occupancy_rate = 0.91 + 0.035 * math.sin((month_date.month + prop_index) / 2.3)
            occupied = max(1, min(prop["units"], round(prop["units"] * occupancy_rate)))
            if not (prop["name"] == "Park Lane" and month == "2026-07"):
                db.upsert_occupancy(conn, pid, month, occupied, prop["units"] - occupied)

            for category, config in UTILITY_CONFIG.items():
                noise = rng.uniform(0.96, 1.04)
                consumption = (
                    occupied * config["base_usage_per_unit"]
                    * seasonal_factor(category, month_date.month) * noise
                )
                years_elapsed = (month_date.year - SEED_START.year) + (month_date.month - 7) / 12
                rate = config["base_rate"] * (1.0 + 0.028 * years_elapsed)

                # Deliberate recent exceptions that exercise the triage screens.
                if prop["name"] == "Cedar Place" and category == "Water" and month in ("2026-06", "2026-07"):
                    consumption *= 1.62
                if prop["name"] == "Riverside Towers" and category == "Electricity" and month in ("2026-06", "2026-07"):
                    rate *= 1.24
                if prop["name"] == "Harbour View" and category == "Natural Gas" and month in ("2026-06", "2026-07"):
                    consumption *= 1.70
                if prop["name"] == "Maple Court" and category == "Water" and month == "2026-06":
                    consumption *= 1.45

                taxes = consumption * rate * 0.13
                total = consumption * rate + taxes
                days = calendar.monthrange(month_date.year, month_date.month)[1]
                fields = {
                    "property_id": pid,
                    "property_name": prop["name"],
                    "category": category,
                    "vendor": config["vendor"],
                    "invoice_number": f"{config['prefix']}-{pid:02d}-{month_date:%Y%m}",
                    "billing_start": f"{month}-01",
                    "billing_end": f"{month}-{days:02d}",
                    "consumption": round(consumption, 1),
                    "consumption_unit": config["unit"],
                    "taxes_fees": round(taxes, 2),
                    "total_cost": round(total, 2),
                    "notes": "Synthetic historical invoice for demonstration and testing.",
                }
                confidence = {
                    key: 0.97 for key in (
                        "vendor", "invoice_number", "category", "billing_start", "billing_end",
                        "consumption", "consumption_unit", "taxes_fees", "total_cost",
                    )
                }
                filename = f"{prop['name'].lower().replace(' ', '_')}_{category.lower().replace(' ', '_')}_{month}.pdf"
                inv_id = add_invoice(conn, fields, filename, approved=True, confidence=confidence)
                invoice_ids[(prop["name"], category, month)] = inv_id
                approved_count += 1

    # August review queue: clean extractions, incomplete scans, and likely duplicates.
    pending_count = 0
    for index, prop in enumerate(PROPERTIES):
        pid = property_rows[prop["name"]]["id"]
        category = ["Water", "Electricity", "Natural Gas"][index % 3]
        config = UTILITY_CONFIG[category]
        fields = {
            "property_id": pid,
            "property_name": prop["name"],
            "category": category,
            "vendor": config["vendor"],
            "invoice_number": f"{config['prefix']}-{pid:02d}-202608",
            "billing_start": "2026-08-01",
            "billing_end": "2026-08-31",
            "consumption": round(prop["units"] * config["base_usage_per_unit"] * seasonal_factor(category, 8), 1),
            "consumption_unit": config["unit"],
            "taxes_fees": 112.45 + index * 18,
            "total_cost": 977.25 + index * 415,
            "notes": "High-confidence extraction waiting for analyst approval.",
        }
        confidence = {key: 0.94 for key in (
            "vendor", "billing_start", "billing_end", "consumption", "consumption_unit", "total_cost"
        )}
        add_invoice(conn, fields, f"review_ready_{index + 1}.pdf", approved=False, confidence=confidence)
        pending_count += 1

    problem_templates = [
        ("Unassigned scanned water bill", None, "Water", "Toronto Water", None, None),
        ("Missing consumption electricity bill", "Cedar Place", "Electricity", "Toronto Hydro", None, 1842.50),
        ("Missing vendor gas bill", "Harbour View", "Natural Gas", "", 822.0, 910.30),
    ]
    for index, (label, property_name, category, vendor, consumption, total_cost) in enumerate(problem_templates):
        prop = property_rows.get(property_name) if property_name else None
        fields = {
            "property_id": prop["id"] if prop else None,
            "property_name": property_name or "Unassigned property",
            "category": category,
            "vendor": vendor,
            "invoice_number": f"PROBLEM-{index + 1}",
            "billing_start": "2026-08-01",
            "billing_end": "2026-08-31",
            "consumption": consumption,
            "consumption_unit": "m3" if consumption else "",
            "taxes_fees": None,
            "total_cost": total_cost,
            "notes": f"{label}. Requires analyst correction.",
        }
        low_conf = {key: 0.18 for key in (
            "vendor", "billing_start", "billing_end", "consumption", "consumption_unit", "total_cost"
        )}
        add_invoice(conn, fields, f"problem_invoice_{index + 1}.pdf", approved=False, confidence=low_conf)
        pending_count += 1

    duplicate_targets = [
        ("Cedar Place", "Water", "2026-07"),
        ("Riverside Towers", "Electricity", "2026-07"),
    ]
    for index, key in enumerate(duplicate_targets):
        original_id = invoice_ids[key]
        original = dict(db.get_invoice(conn, original_id))
        original["property_name"] = key[0]
        original["notes"] = "Possible duplicate copy uploaded for review."
        add_invoice(
            conn, original, f"possible_duplicate_{index + 1}.pdf", approved=False,
            confidence={k: 0.92 for k in (
                "vendor", "billing_start", "billing_end", "consumption", "consumption_unit", "total_cost"
            )},
            logical_duplicate_of=original_id,
        )
        pending_count += 1

    # Persist a few analyst findings and actions so those pages are testable too.
    cedar_id = property_rows["Cedar Place"]["id"]
    riverside_id = property_rows["Riverside Towers"]["id"]
    harbour_id = property_rows["Harbour View"]["id"]

    cedar_finding = db.insert_finding(
        conn, cedar_id, "Water",
        "Cedar Place water consumption remains materially above its seasonal baseline.",
        "June and July usage per occupied unit is approximately 60% above comparable summer periods; occupancy is stable and the effective rate is within its normal range.",
        12600.0, "Inspect common-area fixtures and compare the main meter with suite submeters.",
        severity="High", confidence="Strong", cause="Usage", owner="Nathan",
        source_invoice_ids=[invoice_ids[("Cedar Place", "Water", "2026-06")], invoice_ids[("Cedar Place", "Water", "2026-07")]],
    )
    db.update_finding_status(conn, cedar_finding, "Reviewing")
    db.insert_action(
        conn, cedar_finding, "Arrange a leak inspection and record the main meter reading.",
        owner="Property Manager", due_date="2026-08-28", status="Investigating",
        notes="Analyst requested photos of the meter and maintenance log.", expected_savings=12600.0,
    )

    riverside_finding = db.insert_finding(
        conn, riverside_id, "Electricity",
        "Riverside Towers electricity increase appears rate-driven rather than usage-driven.",
        "June and July consumption is consistent with prior summers, while the effective rate is approximately 24% above baseline.",
        17800.0, "Review the utility rate class and compare the latest bill with the prior contract terms.",
        severity="Medium", confidence="Likely", cause="Rate", owner="Nathan",
        source_invoice_ids=[invoice_ids[("Riverside Towers", "Electricity", "2026-07")]],
    )
    db.update_finding_status(conn, riverside_finding, "Pending")
    db.insert_action(
        conn, riverside_finding, "Request a rate-class explanation from Toronto Hydro.",
        owner="Nathan", due_date="2026-09-04", status="New",
        notes="Waiting for the July statement detail.", expected_savings=17800.0,
    )

    harbour_finding = db.insert_finding(
        conn, harbour_id, "Natural Gas",
        "Harbour View summer gas consumption increased despite stable occupancy.",
        "The increase is isolated to consumption; the gas rate is near the seasonal benchmark.",
        6400.0, "Review domestic hot-water controls and boiler scheduling.",
        severity="High", confidence="Likely", cause="Usage", owner="Building Superintendent",
        source_invoice_ids=[invoice_ids[("Harbour View", "Natural Gas", "2026-07")]],
    )
    db.update_finding_status(conn, harbour_finding, "Recovered")
    harbour_action = db.insert_action(
        conn, harbour_finding, "Correct the domestic hot-water recirculation schedule.",
        owner="Building Superintendent", due_date="2026-08-12", status="Resolved",
        notes="Timer was running continuously and has been corrected.", expected_savings=6400.0,
    )
    db.update_action(conn, harbour_action, confirmed_savings=5900.0)

    summary = {
        "properties": len(PROPERTIES),
        "approved_invoices": approved_count,
        "review_queue": pending_count,
        "findings": conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0],
        "actions": conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0],
        "database": str(db.DB_PATH),
    }
    conn.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true",
        help="Replace all existing demo data. Never affects the production database.",
    )
    args = parser.parse_args()
    print(json.dumps(seed(reset=args.reset), indent=2))


if __name__ == "__main__":
    main()
