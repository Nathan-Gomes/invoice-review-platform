from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import Response, StreamingResponse
import io

from backend.schemas.overview import ThresholdSettings, DismissedPatternOut
from backend.schemas.properties import OccupancyImportRow
from backend.schemas.common import OkResponse
from backend.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=ThresholdSettings)
def get_settings():
    return settings_service.get_thresholds()


@router.patch("", response_model=ThresholdSettings)
def update_settings(payload: ThresholdSettings):
    return settings_service.update_thresholds(payload)


@router.post("/occupancy/preview", response_model=list[OccupancyImportRow])
async def preview_occupancy(file: UploadFile = File(...)):
    content = await file.read()
    return settings_service.preview_occupancy_import(content, file.filename)


@router.post("/occupancy/import")
async def commit_occupancy(file: UploadFile = File(...)):
    content = await file.read()
    return settings_service.commit_occupancy_import(content, file.filename)


@router.post("/backup", response_model=OkResponse)
def create_backup():
    path = settings_service.create_backup()
    return OkResponse(ok=True, message=f"Backup written to {path}")


@router.get("/export")
def export_data():
    zip_bytes = settings_service.export_csv_zip()
    return StreamingResponse(
        io.BytesIO(zip_bytes), media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=invoice_review_export.zip"},
    )


@router.get("/report")
def generate_report(fmt: str = Query(..., description="md | csv | pdf"), month: str | None = Query(None)):
    try:
        content, media_type, filename = settings_service.generate_report(fmt, month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(
        content=content, media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
