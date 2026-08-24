from fastapi import APIRouter
from backend.schemas.overview import OverviewResponse
from backend.services import overview_service

router = APIRouter(prefix="/api/overview", tags=["overview"])


@router.get("", response_model=OverviewResponse)
def get_overview():
    return overview_service.get_overview()
