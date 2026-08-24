from fastapi import APIRouter, Query
from backend.schemas.incidents import ActionOut, ActionUpdate
from backend.services import incidents_service

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("", response_model=list[ActionOut])
def list_actions(finding_id: int | None = Query(None)):
    return incidents_service.list_actions(finding_id=finding_id)


@router.patch("/{action_id}", response_model=ActionOut)
def update_action(action_id: int, payload: ActionUpdate):
    incidents_service.update_action(
        action_id, status=payload.status, notes=payload.notes,
        confirmed_savings=payload.confirmed_savings, owner=payload.owner, due_date=payload.due_date,
    )
    return incidents_service.get_action(action_id)
