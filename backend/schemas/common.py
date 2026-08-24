"""
schemas/common.py — Shared enums and small reusable schemas.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class InvoiceState(str, Enum):
    needs_review = "Needs Review"
    problem = "Problem"
    duplicate = "Duplicate"
    approved = "Approved"
    rejected = "Rejected"


class FindingStatus(str, Enum):
    new = "New"
    reviewing = "Reviewing"
    pending = "Pending"
    recovered = "Recovered"
    closed = "Closed"
    dismissed = "Dismissed"


class ActionStatus(str, Enum):
    new = "New"
    investigating = "Investigating"
    actioned = "Actioned"
    resolved = "Resolved"


class IncidentTier(str, Enum):
    critical = "Critical"
    watch = "Watch"
    informational = "Informational"


class Confidence(str, Enum):
    possible = "Possible"
    likely = "Likely"
    strong = "Strong"


class Severity(str, Enum):
    low = "Low"
    medium = "Medium"
    high = "High"


class Cause(str, Enum):
    usage = "Usage"
    rate = "Rate"
    occupancy = "Occupancy"
    billing = "Billing"
    mixed = "Mixed"
    unknown = "Unknown"


class OkResponse(BaseModel):
    ok: bool = True
    message: Optional[str] = None
