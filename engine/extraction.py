"""
extraction.py — Turns an uploaded PDF or Excel/CSV file into a first-guess
set of invoice fields, each with a confidence score. Confidence drives the
"low-confidence field" highlighting in Review — this parser is a time-saver,
never a replacement for a human checking every value.
"""

import re
import io
import hashlib
from datetime import datetime

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

import pandas as pd


def file_fingerprint(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def extract_pdf_text(file_bytes: bytes) -> tuple[str, bool]:
    """Returns (text, has_extractable_text). False signals a likely scanned PDF."""
    if PdfReader is None:
        return "", False
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = [(p.extract_text() or "") for p in reader.pages]
    full_text = "\n".join(pages_text).strip()
    return full_text, len(full_text) > 20


_MONEY = r"\$?\s?([\d,]+\.\d{2})"
_DATE = r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"

# Each field has a list of (pattern, confidence) tried in order — first match wins,
# and its confidence travels with it so the Review screen can flag weak guesses.
PATTERNS = {
    "invoice_number": [
        (r"invoice\s*(?:#|number|no\.?)\s*[:\-]?\s*([A-Za-z0-9\-]+)", 0.95),
        (r"account\s*(?:#|number|no\.?)\s*[:\-]?\s*([A-Za-z0-9\-]+)", 0.6),
    ],
    "total_cost": [
        (r"total\s*amount\s*due\s*[:\-]?\s*" + _MONEY, 0.95),
        (r"amount\s*due\s*[:\-]?\s*" + _MONEY, 0.9),
        (r"total\s*(?:amount|cost)?\s*[:\-]?\s*" + _MONEY, 0.6),
    ],
    "taxes_fees": [
        (r"tax(?:es)?\s*[:\-]?\s*" + _MONEY, 0.85),
        (r"fees?\s*[:\-]?\s*" + _MONEY, 0.6),
    ],
    "billing_start": [
        (r"(?:billing|service)\s*period\s*[:\-]?\s*" + _DATE, 0.9),
        (r"from\s*[:\-]?\s*" + _DATE, 0.6),
    ],
    "billing_end": [
        (r"to\s*[:\-]?\s*" + _DATE, 0.6),
        (r"through\s*[:\-]?\s*" + _DATE, 0.6),
    ],
}

CONSUMPTION_PATTERNS = [
    (r"([\d,]+\.?\d*)\s*(kwh)", "kWh", 0.9),
    (r"([\d,]+\.?\d*)\s*(gallons?|gal\b)", "gallons", 0.9),
    # Gas units are NOT interchangeable — 1 CCF =/= 1 therm =/= 1 m3 =/= 1
    # cubic foot. Each gets its own correct label; engine/units.py converts
    # between them for analysis math, but the invoice's actual recorded
    # unit is preserved here rather than silently mislabeled.
    (r"([\d,]+\.?\d*)\s*(ccf)", "CCF", 0.85),
    (r"([\d,]+\.?\d*)\s*(therms?)", "therms", 0.85),
    (r"([\d,]+\.?\d*)\s*(cubic\s*met(?:er|re)s?|m3|m\u00b3)", "m3", 0.85),
    (r"([\d,]+\.?\d*)\s*(cubic\s*feet|cu\.?\s*ft\.?)", "cubic feet", 0.8),
]

VENDOR_HINTS = [
    (r"^([A-Z][A-Za-z&,.\s]{2,40}(?:Water|Electric|Power|Gas|Utilities|Utility|Company|Co\.|Inc\.|LLC|Ltd\.?))", 0.75),
]


def _first_match(patterns, text, flags=re.IGNORECASE):
    """patterns: list of (pattern, confidence). Returns (value, confidence) or (None, 0.0)."""
    for pat, conf in patterns:
        m = re.search(pat, text, flags)
        if m:
            return m.group(1).strip(), conf
    return None, 0.0


def _normalize_date(raw):
    if not raw:
        return ""
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw.replace(",", ""), fmt.replace(",", "")).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def guess_category(text: str) -> tuple[str, float]:
    t = text.lower()
    if "water" in t or "sewer" in t:
        return "Water", 0.7
    if "electric" in t or "kwh" in t:
        return "Electricity", 0.7
    if "gas" in t and "garage" not in t:
        return "Natural Gas", 0.7
    return "Other", 0.2


def parse_invoice_fields(text: str) -> tuple[dict, dict]:
    """
    Returns (fields, confidence) — confidence is a dict of field_name -> 0.0-1.0,
    used by Review to highlight anything the parser is unsure about.
    """
    fields = {
        "vendor": "", "invoice_number": "", "category": "",
        "billing_start": "", "billing_end": "",
        "consumption": None, "consumption_unit": "",
        "taxes_fees": None, "total_cost": None, "notes": "",
    }
    confidence = {k: 0.0 for k in fields}

    category, cat_conf = guess_category(text)
    fields["category"] = category
    confidence["category"] = cat_conf

    vendor, vconf = _first_match(VENDOR_HINTS, text, flags=re.MULTILINE)
    if vendor:
        fields["vendor"] = vendor
        confidence["vendor"] = vconf

    inv_num, iconf = _first_match(PATTERNS["invoice_number"], text)
    if inv_num:
        fields["invoice_number"] = inv_num
        confidence["invoice_number"] = iconf

    total, tconf = _first_match(PATTERNS["total_cost"], text)
    if total:
        fields["total_cost"] = float(total.replace(",", ""))
        confidence["total_cost"] = tconf

    taxes, txconf = _first_match(PATTERNS["taxes_fees"], text)
    if taxes:
        fields["taxes_fees"] = float(taxes.replace(",", ""))
        confidence["taxes_fees"] = txconf

    b_start, bsconf = _first_match(PATTERNS["billing_start"], text)
    if b_start:
        fields["billing_start"] = _normalize_date(b_start)
        confidence["billing_start"] = bsconf

    b_end, beconf = _first_match(PATTERNS["billing_end"], text)
    if b_end:
        fields["billing_end"] = _normalize_date(b_end)
        confidence["billing_end"] = beconf

    for pattern, unit, cconf in CONSUMPTION_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            fields["consumption"] = float(m.group(1).replace(",", ""))
            fields["consumption_unit"] = unit
            confidence["consumption"] = cconf
            confidence["consumption_unit"] = cconf
            break

    if not text.strip():
        fields["notes"] = "No extractable text found — likely a scanned PDF. Needs OCR or manual entry."

    return fields, confidence


def read_tabular_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(file_bytes))
    return pd.read_excel(io.BytesIO(file_bytes))
