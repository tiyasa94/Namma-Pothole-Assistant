"""
POST /reports — submit a new pothole report.

Flow:
  1. Persist a new PotholeReport row with status=pending.
  2. Dispatch ML analysis asynchronously (background task).
  3. Return the report_id and h3_cell immediately so the mobile client
     can display confirmation without waiting for ML inference.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.ml_engine.detector import PotholeMLEngine, get_ml_engine
from api.models.orm import PotholeReport, RoadSegment
from api.models.schemas import ReportCreate, ReportResponse
from api.services.geo import lat_lng_to_h3
from api.services.scoring import PotholeEntry, compute_road_quality_score
from api.services.storage import save_image_base64

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_id}", tags=["reports"])
async def get_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Fetch a single report by ID — used by the UI to poll ML verification status."""
    from sqlalchemy import select
    stmt = select(PotholeReport).where(PotholeReport.id == report_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "report_id":       str(row.id),
        "status":          row.status,
        "severity":        row.severity,
        "user_severity_hint": row.user_severity_hint,
        "ml_confidence":   row.ml_confidence,
        "pixel_area_pct":  row.pixel_area_pct,
        "h3_cell":         row.h3_index_r9,
        "image_url":       row.image_url,
        "description":     row.description,
        "reported_at":     row.reported_at.isoformat() if row.reported_at else None,
    }


# ── Background: run ML + update report ────────────────────────────────────────

async def _run_ml_and_update(
    report_id: uuid.UUID,
    image_base64: str,
    db: AsyncSession,
    engine: PotholeMLEngine,
):
    """
    Runs ML inference and patches the report row with results.
    Called as a BackgroundTask so the initial POST returns immediately.
    """
    result = await engine.analyse(image_base64)

    # Fetch the saved report
    stmt = select(PotholeReport).where(PotholeReport.id == report_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        logger.error("Report %s vanished before ML update", report_id)
        return

    if result.detected:
        row.severity = result.severity
        row.ml_confidence = result.confidence
        row.pixel_area_pct = result.pixel_area_pct
        row.status = "verified"
    else:
        row.status = "archived"  # not a pothole — archive rather than delete

    await db.commit()
    logger.info(
        "ML update complete for report %s: detected=%s severity=%s",
        report_id,
        result.detected,
        result.severity,
    )

    # Trigger road-segment quality score refresh if a segment is linked
    if row.road_segment_id:
        await _refresh_segment_score(row.road_segment_id, db)


async def _refresh_segment_score(segment_id: uuid.UUID, db: AsyncSession):
    """Recompute the quality_score for a road segment after a new report."""
    from datetime import timezone

    stmt = select(PotholeReport).where(
        PotholeReport.road_segment_id == segment_id,
        PotholeReport.status == "verified",
    )
    reports = (await db.execute(stmt)).scalars().all()

    entries = [
        PotholeEntry(
            severity=r.severity or "low",
            reported_at=r.reported_at.replace(tzinfo=timezone.utc)
            if r.reported_at.tzinfo is None
            else r.reported_at,
            ml_confidence=r.ml_confidence or 1.0,
        )
        for r in reports
    ]

    score = compute_road_quality_score(entries)

    seg_stmt = select(RoadSegment).where(RoadSegment.id == segment_id)
    segment = (await db.execute(seg_stmt)).scalar_one_or_none()
    if segment:
        segment.quality_score = score
        segment.pothole_count = len(entries)
        await db.commit()


# ── Route handler ──────────────────────────────────────────────────────────────

@router.post("/", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    ml_engine: PotholeMLEngine = Depends(get_ml_engine),
):
    """Submit a new pothole report and trigger async ML verification."""
    h3_cell = lat_lng_to_h3(body.lat, body.lng)

    # Snap to nearest road segment (PostGIS: closest linestring within 100m)
    snap_sql = text(
        """
        SELECT id FROM road_segments
        WHERE ST_DWithin(
            geometry,
            ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
            100
        )
        ORDER BY ST_Distance(
            geometry,
            ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
        )
        LIMIT 1
        """
    )
    snap_result = await db.execute(snap_sql, {"lat": body.lat, "lng": body.lng})
    segment_row = snap_result.fetchone()
    road_segment_id = segment_row[0] if segment_row else None

    # A photo is required. Reject invalid image data instead of creating a
    # report that cannot be verified by the ML engine.
    try:
        image_url = save_image_base64(body.image_base64, "pending")
    except Exception as exc:
        logger.warning("Image save failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded photo could not be read. Please upload a JPG or PNG image.",
        ) from exc

    # Persist initial pending record
    report = PotholeReport(
        location=f"SRID=4326;POINT({body.lng} {body.lat})",
        h3_index_r9=h3_cell,
        road_segment_id=road_segment_id,
        source=body.source,
        description=body.description,
        image_url=image_url,
        user_severity_hint=body.severity_hint,
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    # Photo is required, so every report is sent for background ML analysis.
    background_tasks.add_task(
        _run_ml_and_update,
        report.id,
        body.image_base64,
        db,
        ml_engine,
    )

    return ReportResponse(
        report_id=report.id,
        status="pending_verification",
        h3_cell=h3_cell,
        road_segment_id=road_segment_id,
        estimated_verification_time_seconds=30,
    )
