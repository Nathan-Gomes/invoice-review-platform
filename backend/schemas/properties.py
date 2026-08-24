"""
schemas/properties.py
"""

from typing import Optional
from pydantic import BaseModel


class PropertyOut(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    units: Optional[int] = None
    sqft: Optional[int] = None
    construction_year: Optional[int] = None
    heating_type: Optional[str] = None
    metering_type: Optional[str] = None


class PropertyCreate(BaseModel):
    name: str
    address: str = ""
    units: Optional[int] = None
    sqft: Optional[int] = None
    construction_year: Optional[int] = None
    heating_type: str = ""
    metering_type: str = ""


class CategoryMonthMetrics(BaseModel):
    category: str
    month: str
    total_cost: float
    occupied_units: Optional[int] = None
    cost_per_occupied_unit: Optional[float] = None
    consumption_per_occupied_unit: Optional[float] = None
    usage_per_unit_per_day: Optional[float] = None
    effective_rate: Optional[float] = None
    yoy_variance_pct: Optional[float] = None
    expected_cost: Optional[float] = None
    observed_excess: Optional[float] = None
    cause: str
    baseline_method: Optional[str] = None
    baseline_confidence: str
    explanation: str


class TrendPoint(BaseModel):
    month: str
    total_cost: float
    expected_cost: Optional[float] = None
    invoice_id: int


class PropertyDetail(BaseModel):
    property: PropertyOut
    current_month_by_category: list[CategoryMonthMetrics]
    open_incident_count: int


class OccupancyOut(BaseModel):
    property_id: int
    property_name: Optional[str] = None
    month: str
    occupied_units: int
    vacant_units: int


class OccupancyUpsert(BaseModel):
    property_id: int
    month: str
    occupied_units: int
    vacant_units: int


class OccupancyImportRow(BaseModel):
    property_name: str
    month: str
    occupied_units: int
    vacant_units: int
    valid: bool
    reason: Optional[str] = None
