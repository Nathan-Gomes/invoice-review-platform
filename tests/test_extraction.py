"""
Extraction regression tests (item 15). Run with: pytest tests/test_extraction.py

These fixtures are synthetic/anonymized, standing in for real invoice layouts
until 15-30 real (anonymized) invoices are available — at that point, add
them to fixtures/ and a matching test here so a future regex change can't
silently break extraction on a layout that used to work.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import extraction

FIXTURES = Path(__file__).parent.parent / "engine" / "fixtures"


def _load(name):
    return (FIXTURES / name).read_text()


def test_water_invoice_clean_layout():
    text = _load("water_invoice_1.txt")
    fields, confidence = extraction.parse_invoice_fields(text)

    assert fields["category"] == "Water"
    assert fields["invoice_number"] == "WU-88213"
    assert fields["billing_start"] == "2026-01-01"
    assert fields["billing_end"] == "2026-01-31"
    assert fields["consumption"] == 45230.0
    assert fields["consumption_unit"] == "gallons"
    assert fields["taxes_fees"] == 12.40
    assert fields["total_cost"] == 412.55
    # invoice number matched via the strict pattern -> high confidence
    assert confidence["invoice_number"] >= 0.9
    assert confidence["total_cost"] >= 0.9


def test_electricity_invoice_different_layout():
    text = _load("electricity_invoice_1.txt")
    fields, confidence = extraction.parse_invoice_fields(text)

    assert fields["category"] == "Electricity"
    assert fields["consumption"] == 12400.0
    assert fields["consumption_unit"] == "kWh"
    assert fields["total_cost"] == 1844.22
    # "Account Number" is the weaker fallback pattern for invoice_number
    assert fields["invoice_number"] == "4471-982-01"
    assert confidence["invoice_number"] < 0.9


def test_sparse_gas_invoice_flags_low_confidence():
    text = _load("gas_invoice_sparse.txt")
    fields, confidence = extraction.parse_invoice_fields(text)

    assert fields["category"] == "Natural Gas"
    assert fields["consumption"] == 980.0
    assert fields["consumption_unit"] == "therms"
    # no "Invoice #" or "Total Amount Due" phrasing present -> low/no confidence
    assert confidence["invoice_number"] == 0.0
    assert fields["invoice_number"] == ""


def test_ccf_gas_invoice_extracted_as_ccf_not_collapsed():
    """Regression test: CCF, therms, and m3 used to be collapsed into one
    fictional 'therms/m3' unit even though they're not interchangeable
    (1 CCF =/= 1 therm =/= 1 m3). Each must extract with its own real unit."""
    text = _load("gas_invoice_ccf.txt")
    fields, confidence = extraction.parse_invoice_fields(text)

    assert fields["category"] == "Natural Gas"
    assert fields["consumption"] == 45.6
    assert fields["consumption_unit"] == "CCF"
    assert confidence["consumption_unit"] > 0


def test_m3_gas_invoice_extracted_as_m3_not_collapsed():
    text = _load("gas_invoice_m3.txt")
    fields, confidence = extraction.parse_invoice_fields(text)

    assert fields["category"] == "Natural Gas"
    assert fields["consumption"] == 129.0
    assert fields["consumption_unit"] == "m3"
    assert confidence["consumption_unit"] > 0


def test_scanned_blank_pdf_flags_notes():
    text = _load("scanned_blank.txt")
    fields, confidence = extraction.parse_invoice_fields(text)

    assert "scanned" in fields["notes"].lower() or "no extractable text" in fields["notes"].lower()
    assert fields["total_cost"] is None


def test_duplicate_fingerprint_is_stable():
    a = extraction.file_fingerprint(b"hello world")
    b = extraction.file_fingerprint(b"hello world")
    c = extraction.file_fingerprint(b"hello WORLD")
    assert a == b
    assert a != c
