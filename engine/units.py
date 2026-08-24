"""
units.py — Unit conversion for natural gas consumption.

CCF, therms, cubic meters, and cubic feet are NOT interchangeable, but a
single property's invoices can arrive in different units over time (e.g. a
vendor switch, or a utility that changed its billing format). Any
consumption-per-unit comparison, baseline average, or effective-rate
calculation that mixes raw numbers across these units without converting
first produces a meaningless result — "50 CCF" and "50 m3" are very
different quantities of gas.

Conversion factors below use standard, widely-cited approximations (natural
gas heat content varies slightly by region/utility, so these are industry-
typical figures, not universal physical constants):

- 1 CCF (100 cubic feet)  ≈ 1.037 therms
- 1 therm                  = 1 therm (identity)
- 1 m3 (cubic meter)       ≈ 0.3661 therms  (≈ 35.3147 cubic feet, ≈ 1.037 therms/CCF)
- 1 cubic foot             ≈ 0.01037 therms (1/100th of a CCF)

Water (gallons) and electricity (kWh) currently have only one extraction
unit each, so no conversion table exists for them yet — normalize_gas_consumption
is a no-op passthrough for any unit it doesn't recognize as a gas unit, so
calling it on water/electric consumption is always safe.
"""

GAS_UNIT_TO_THERMS = {
    "ccf": 1.037,
    "therms": 1.0,
    "therm": 1.0,
    "m3": 0.3661,
    "cubic feet": 0.01037,
}

CANONICAL_GAS_UNIT = "therms"


def normalize_gas_consumption(value, unit):
    """
    Converts a gas consumption value to therms (the canonical unit used
    internally for any cross-invoice comparison). Returns None if the value
    is missing, and returns the value unchanged if the unit isn't a
    recognized gas unit (so this is always safe to call on water/electric
    consumption too — it simply won't convert those).
    """
    if value is None:
        return None
    if unit is None:
        return value
    factor = GAS_UNIT_TO_THERMS.get(unit.strip().lower())
    if factor is None:
        return value
    return value * factor


def is_gas_unit(unit) -> bool:
    if not unit:
        return False
    return unit.strip().lower() in GAS_UNIT_TO_THERMS
