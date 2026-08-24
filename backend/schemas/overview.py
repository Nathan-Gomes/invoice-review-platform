"""
schemas/overview.py and settings-related schemas.
"""

from typing import Optional
from pydantic import BaseModel


class OverviewMetrics(BaseModel):
    total_monthly_spend: float
    yoy_variance_pct: Optional[float] = None
    estimated_annual_excess: float
    invoices_needing_review: int
    open_critical_incidents: int
    open_watch_incidents: int


class NeedsAttentionRow(BaseModel):
    property_id: int
    property_name: str
    category: str
    tier: str
    severity: str
    confidence: str
    issue: str
    cause: str
    annualized_impact: float
    latest_month: str


class PortfolioTrendPoint(BaseModel):
    month: str
    total_cost: float


class CategoryBreakdown(BaseModel):
    category: str
    total_cost: float


class PropertyRanking(BaseModel):
    property_id: int
    property_name: str
    observed_excess: float


class RecentAction(BaseModel):
    id: int
    property_name: Optional[str] = None
    action_taken: str
    owner: Optional[str] = None
    status: str
    due_date: Optional[str] = None


class OverviewResponse(BaseModel):
    metrics: OverviewMetrics
    needs_attention: list[NeedsAttentionRow]
    portfolio_trend: list[PortfolioTrendPoint]
    category_breakdown: list[CategoryBreakdown]
    top_properties_by_excess: list[PropertyRanking]
    recent_actions: list[RecentAction]


class ThresholdSettings(BaseModel):
    threshold_yoy_pct: float
    threshold_usage_pct: float
    threshold_rate_pct: float
    threshold_sustained_months: int
    threshold_stddev: float


class DismissedPatternOut(BaseModel):
    id: int
    property_id: int
    property_name: Optional[str] = None
    category: str
    rule: str
    reason: Optional[str] = None
    created_at: str
