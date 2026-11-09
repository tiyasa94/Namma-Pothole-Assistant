"""
POST /v1/voice-report — submit a pothole report via voice audio.

Supports:
  - English (en-IN)
  - Hindi (hi-IN)
  - Kannada (kn-IN)

Flow:
  1. Decode base64 audio.
  2. Transcribe using Google Speech Recognition (free, no key needed).
  3. Detect language from transcribed text.
  4. Translate non-English text to English.
  5. Persist a PotholeReport with source="voice" and the English description.
  6. Return transcription details + report_id immediately.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.ml_engine.detector import PotholeMLEngine, get_ml_engine
from api.models.orm import PotholeReport
from api.models.schemas import VoiceReportCreate, VoiceReportResponse
from api.services.geo import lat_lng_to_h3
from api.services.voice import transcribe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice-report", tags=["voice"])


@router.post("/", response_model=VoiceReportResponse, status_code=status.HTTP_201_CREATED)
async def create_voice_report(
    body: VoiceReportCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    ml_engine: PotholeMLEngine = Depends(get_ml_engine),
):
    """
    Submit a pothole report via voice audio (English / Hindi / Kannada).

    The audio is transcribed, translated to English if needed, and stored
    as a pothole report with source='voice'.
    """
    # ── Step 1: transcribe audio ───────────────────────────────────────────────
    transcript = await transcribe(body.audio_base64, language_hint=body.language_hint)

    if transcript.error and not transcript.original_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Transcription failed: {transcript.error}",
        )

    # ── Step 2: snap to nearest road segment ──────────────────────────────────
    h3_cell = lat_lng_to_h3(body.lat, body.lng)

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

    # ── Step 3: persist report ────────────────────────────────────────────────
    report = PotholeReport(
        location=f"SRID=4326;POINT({body.lng} {body.lat})",
        h3_index_r9=h3_cell,
        road_segment_id=road_segment_id,
        source="voice",
        # Store English text as description for downstream ML/search
        description=transcript.english_text or transcript.original_text,
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    logger.info(
        "Voice report %s created | lang=%s | text=%r | english=%r",
        report.id,
        transcript.detected_language,
        transcript.original_text[:60],
        transcript.english_text[:60],
    )

    return VoiceReportResponse(
        report_id=report.id,
        status="pending_verification",
        h3_cell=h3_cell,
        road_segment_id=road_segment_id,
        original_text=transcript.original_text,
        detected_language=transcript.detected_language,
        language_name=transcript.language_name,
        english_text=transcript.english_text,
        transcription_confidence=transcript.confidence,
        estimated_verification_time_seconds=30,
    )
