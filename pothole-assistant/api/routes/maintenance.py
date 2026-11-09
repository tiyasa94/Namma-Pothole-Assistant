"""
POST /maintenance — log a maintenance event (BBMP operator auth required).

In prototype mode, auth is a simple Bearer token header check.
In production, replace with Firebase Auth custom claims middleware.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.database import get_db
from api.models.orm import MaintenanceLog
from api.models.schemas import MaintenanceCreate, MaintenanceResponse

router = APIRouter(prefix="/maintenance", tags=["maintenance"])
settings = get_settings()

_bearer = HTTPBearer()


# ── Prototype auth guard ───────────────────────────────────────────────────────

def _require_bbmp_token(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    """
    Validates the BBMP operator bearer token.
    Prototype: accepts the SECRET_KEY from config as the token.
    Using FastAPI's HTTPBearer makes the 🔒 Authorize button in Swagger work.
    """
    if credentials.credentials != settings.SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid BBMP operator token",
        )


# ── Route handler ──────────────────────────────────────────────────────────────

@router.post("/", response_model=MaintenanceResponse, status_code=status.HTTP_201_CREATED)
async def log_maintenance(
    body: MaintenanceCreate,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(_require_bbmp_token),
):
    """Log a road maintenance event by a BBMP operator."""
    # Build WKT polygon from affected_bbox [[lat1,lng1],[lat2,lng2]] corners
    bbox_wkt = None
    if body.affected_bbox and len(body.affected_bbox) >= 2:
        c = body.affected_bbox
        # Use first two points as SW and NE corners → build all 4 corners
        lat1, lng1 = c[0][0], c[0][1]
        lat2, lng2 = c[1][0], c[1][1]
        min_lat, max_lat = min(lat1, lat2), max(lat1, lat2)
        min_lng, max_lng = min(lng1, lng2), max(lng1, lng2)
        # 5-point closed ring: SW → SE → NE → NW → SW
        pts = (
            f"{min_lng} {min_lat}, "
            f"{max_lng} {min_lat}, "
            f"{max_lng} {max_lat}, "
            f"{min_lng} {max_lat}, "
            f"{min_lng} {min_lat}"
        )
        bbox_wkt = f"SRID=4326;POLYGON(({pts}))"

    log = MaintenanceLog(
        road_segment_id=body.road_segment_id,
        work_type=body.work_type,
        status=body.status,
        notes=body.notes,
        affected_bbox=bbox_wkt,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    return MaintenanceResponse(maintenance_id=log.id, status=log.status)
