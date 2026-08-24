from fastapi import APIRouter, HTTPException, Query
from backend.schemas.properties import (
    PropertyOut, PropertyCreate, PropertyDetail, CategoryMonthMetrics,
    TrendPoint, OccupancyOut, OccupancyUpsert,
)
from backend.schemas.common import OkResponse
from backend.services import properties_service

router = APIRouter(prefix="/api/properties", tags=["properties"])


@router.get("", response_model=list[PropertyOut])
def list_properties():
    return properties_service.list_properties()


@router.post("", response_model=PropertyOut)
def create_property(payload: PropertyCreate):
    return properties_service.create_property(payload)


@router.get("/{property_id}", response_model=PropertyDetail)
def get_property(property_id: int):
    detail = properties_service.get_property_detail(property_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Property not found")
    return detail


@router.get("/{property_id}/analysis", response_model=CategoryMonthMetrics)
def get_property_analysis(property_id: int, category: str = Query(...), month: str = Query(...)):
    metrics = properties_service.get_property_category_metrics(property_id, category, month)
    if not metrics:
        raise HTTPException(status_code=404, detail="No data for this property/category/month")
    return metrics


@router.get("/{property_id}/months", response_model=list[str])
def get_property_months(property_id: int, category: str = Query(...)):
    return properties_service.list_property_months(property_id, category)


@router.get("/{property_id}/trend", response_model=list[TrendPoint])
def get_property_trend(property_id: int, category: str = Query(...), months_back: int = Query(12)):
    return properties_service.get_property_trend(property_id, category, months_back)


@router.get("/{property_id}/occupancy", response_model=list[OccupancyOut])
def get_property_occupancy(property_id: int):
    return properties_service.list_occupancy(property_id=property_id)


@router.post("/occupancy", response_model=OkResponse)
def upsert_occupancy(payload: OccupancyUpsert):
    result = properties_service.upsert_occupancy(
        payload.property_id, payload.month, payload.occupied_units, payload.vacant_units
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return OkResponse(ok=True)
