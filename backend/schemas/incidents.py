"""
schemas/incidents.py — also covers findings and actions, since they're
tightly coupled workflows (incident -> finding -> action).
"""

from typing import Optional
from pydantic import BaseModel


class IncidentOut(BaseModel):
    property_id: int
    property_name: str
    category: str
    months: list[str]
    latest_month: str
    rules: list[str]
    severity: str
    confidence: str
    cause: str
    tier: str
    observed_excess_monthly: float
    annualized_impact: float
    score: float
    messages: list[str]
    is_data_quality_only: bool
    explanation: Optional[str] = None
    primary_invoice_id: Optional[int] = None


class DismissIncidentRequest(BaseModel):
    property_id: int
    category: str
    rules: list[str]
    reason: str = ""


class ConfirmIncidentRequest(BaseModel):
    property_id: int
    category: str
    rules: list[str]
    recommended_action: Optional[str] = None
    set_status: str = "Reviewing"  # Reviewing for confirm/investigate


class FindingOut(BaseModel):
    id: int
    property_id: Optional[int] = None
    property_name: Optional[str] = None
    category: str
    description: str
    evidence: str
    observed_excess: Optional[float] = None
    recommended_action: str
    severity: str
    confidence: str
    cause: str
    owner: Optional[str] = None
    status: str
    source_invoice_ids: list[int] = []
    dismissed_reason: Optional[str] = None
    created_at: str


class FindingStatusUpdate(BaseModel):
    status: str
    dismissed_reason: Optional[str] = None


class ActionCreate(BaseModel):
    finding_id: int
    action_taken: str
    owner: str = ""
    due_date: str = ""
    expected_savings: Optional[float] = None
    notes: str = ""


class ActionOut(BaseModel):
    id: int
    finding_id: int
    finding_description: Optional[str] = None
    property_id: Optional[int] = None
    property_name: Optional[str] = None
    action_taken: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    status: str
    notes: Optional[str] = None
    expected_savings: Optional[float] = None
    confirmed_savings: Optional[float] = None
    created_at: Optional[str] = None


class ActionUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    confirmed_savings: Optional[float] = None
    owner: Optional[str] = None
    due_date: Optional[str] = None
