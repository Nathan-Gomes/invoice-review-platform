from fastapi import APIRouter, Query
from backend.schemas.incidents import FindingOut, FindingStatusUpdate, ActionCreate, ActionOut
from backend.schemas.common import OkResponse
from backend.services import incidents_service

router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.get("", response_model=list[FindingOut])
def list_findings(status: str | None = Query(None)):
    return incidents_service.list_findings(status=status)


@router.patch("/{finding_id}/status", response_model=OkResponse)
def update_finding_status(finding_id: int, payload: FindingStatusUpdate):
    incidents_service.update_finding_status(finding_id, payload.status, payload.dismissed_reason)
    return OkResponse(ok=True)


@router.post("/{finding_id}/actions", response_model=ActionOut)
def create_action_for_finding(finding_id: int, payload: ActionCreate):
    action_id = incidents_service.create_action(
        finding_id, payload.action_taken, payload.owner, payload.due_date,
        payload.expected_savings, payload.notes,
    )
    return incidents_service.get_action(action_id)
