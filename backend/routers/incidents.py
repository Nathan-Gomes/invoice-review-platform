from fastapi import APIRouter, HTTPException, Query
from backend.schemas.incidents import (
    IncidentOut, DismissIncidentRequest, ConfirmIncidentRequest,
)
from backend.schemas.overview import DismissedPatternOut
from backend.schemas.common import OkResponse
from backend.services import incidents_service

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    tier: str | None = Query(None, description="Critical | Watch | Informational"),
    property_id: int | None = Query(None),
    category: str | None = Query(None),
):
    return incidents_service.list_incidents(tier=tier, property_id=property_id, category=category)


@router.post("/scan", response_model=list[IncidentOut])
def rescan_incidents():
    """Re-runs the triage scan. Incidents are computed on read, so this is
    equivalent to GET /api/incidents — kept as a distinct endpoint to match
    the "explicit rescan" action in the UI."""
    return incidents_service.list_incidents()


@router.post("/dismiss", response_model=OkResponse)
def dismiss_incident(payload: DismissIncidentRequest):
    ok = incidents_service.dismiss_incident(payload.property_id, payload.category, payload.rules, payload.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Incident not found (already resolved or scan is stale)")
    return OkResponse(ok=True)


@router.post("/confirm")
def confirm_incident(payload: ConfirmIncidentRequest):
    finding_id = incidents_service.confirm_incident(
        payload.property_id, payload.category, payload.rules,
        payload.recommended_action, payload.set_status,
    )
    if finding_id is None:
        raise HTTPException(status_code=404, detail="Incident not found (already resolved or scan is stale)")
    return {"ok": True, "finding_id": finding_id}


@router.get("/dismissed-patterns", response_model=list[DismissedPatternOut])
def get_dismissed_patterns():
    return incidents_service.list_dismissed_patterns()


@router.delete("/dismissed-patterns/{pattern_id}", response_model=OkResponse)
def delete_dismissed_pattern(pattern_id: int):
    incidents_service.remove_dismissed_pattern(pattern_id)
    return OkResponse(ok=True)
