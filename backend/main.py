"""
backend/main.py — FastAPI application entrypoint.

Run with:  uvicorn backend.main:app --reload --port 8000
(run from the invoice_app/ project root so `engine` and `backend` are importable)
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from engine import db as db_module
from backend.routers import overview, properties, invoices, incidents, findings, actions, settings

db_module.init_db()

app = FastAPI(title="Invoice Review API", version="0.1.0")


@app.middleware("http")
async def protect_public_demo(request, call_next):
    """Keep the public portfolio deployment useful without exposing writes."""
    read_only = os.environ.get("PUBLIC_DEMO_READ_ONLY", "0") == "1"
    if read_only and request.method not in {"GET", "HEAD", "OPTIONS"}:
        return JSONResponse(
            status_code=403,
            content={"detail": "This public portfolio demo is read-only."},
        )
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(overview.router)
app.include_router(properties.router)
app.include_router(invoices.router)
app.include_router(incidents.router)
app.include_router(findings.router)
app.include_router(actions.router)
app.include_router(settings.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "environment": db_module.ENV}
