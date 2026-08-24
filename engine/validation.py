"""
validation.py — Field-level validation for the Review screen, and logical
duplicate / overlapping-period detection that goes beyond file-hash matching
(a rescanned or reformatted copy of the same invoice has a different hash,
but the same vendor/invoice number/property/period/amount).
"""

from datetime import date

REQUIRED_FIELDS = [
    "property_id", "category", "vendor",
    "billing_start", "billing_end", "consumption",
    "consumption_unit", "total_cost",
]

FIELD_LABELS = {
    "property_id": "Property",
    "category": "Category",
    "vendor": "Vendor",
    "billing_start": "Billing start date",
    "billing_end": "Billing end date",
    "consumption": "Consumption",
    "consumption_unit": "Consumption unit",
    "total_cost": "Total cost",
}


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def validate_invoice(fields: dict) -> list[str]:
    """
    Returns a list of human-readable validation errors. Empty list means the
    invoice is approvable. This is the single source of truth the Review
    screen uses to decide whether the Approve button is enabled.
    """
    errors = []

    for f in REQUIRED_FIELDS:
        value = fields.get(f)
        if f in ("consumption", "total_cost", "consumption_unit"):
            continue  # these three have their own explicit checks below
        if value in (None, "", 0):
            errors.append(f"Missing {FIELD_LABELS[f]}")

    if fields.get("total_cost") in (None, 0, 0.0):
        errors.append("Total cost is zero or missing")

    if fields.get("consumption") in (None, 0, 0.0):
        errors.append("Missing consumption")
    elif not fields.get("consumption_unit"):
        errors.append("Missing consumption unit")

    start = _parse_date(fields.get("billing_start"))
    end = _parse_date(fields.get("billing_end"))
    if fields.get("billing_start") and start is None:
        errors.append("Billing start date is not a valid date (expected YYYY-MM-DD)")
    if fields.get("billing_end") and end is None:
        errors.append("Billing end date is not a valid date (expected YYYY-MM-DD)")
    if start and end and end < start:
        errors.append("Billing end date is before billing start date")

    return errors


def find_logical_duplicates(conn, fields: dict, exclude_id=None):
    """
    Flags invoices for the same property+category that share a vendor and
    invoice number, or the same vendor+amount+overlapping billing period.
    Returns a list of dicts: {"invoice": sqlite3.Row, "reason": str} so the
    UI can explain *why* something was flagged, not just that it was.
    """
    from engine import db as db_module

    if not fields.get("property_id") or not fields.get("category"):
        return []

    candidates = db_module.list_invoices_for_duplicate_check(
        conn, fields["property_id"], fields["category"], exclude_id=exclude_id
    )

    matches = []
    start = _parse_date(fields.get("billing_start"))
    end = _parse_date(fields.get("billing_end"))

    for c in candidates:
        same_vendor = (c["vendor"] or "").strip().lower() == (fields.get("vendor") or "").strip().lower()
        if not same_vendor or not c["vendor"]:
            continue

        # Match 1: same invoice number
        if fields.get("invoice_number") and c["invoice_number"] == fields.get("invoice_number"):
            matches.append({
                "invoice": c,
                "reason": (
                    f"Same vendor ('{c['vendor']}') and invoice number "
                    f"('{c['invoice_number']}') as invoice #{c['id']}."
                ),
            })
            continue

        # Match 2: same amount and overlapping billing period
        c_start = _parse_date(c["billing_start"])
        c_end = _parse_date(c["billing_end"])
        same_amount = (
            c["total_cost"] is not None
            and fields.get("total_cost") is not None
            and abs(c["total_cost"] - fields["total_cost"]) < 0.01
        )
        overlaps = (
            start and end and c_start and c_end
            and start <= c_end and c_start <= end
        )
        if same_amount and overlaps:
            matches.append({
                "invoice": c,
                "reason": (
                    f"Same vendor ('{c['vendor']}') and amount (${c['total_cost']:,.2f}) with a "
                    f"billing period overlapping invoice #{c['id']} "
                    f"({c['billing_start']} \u2192 {c['billing_end']})."
                ),
            })

    return matches
