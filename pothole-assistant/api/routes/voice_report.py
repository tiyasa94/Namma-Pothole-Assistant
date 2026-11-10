"""Transcribe a voice description for the pothole report form."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.models.schemas import VoiceReportCreate, VoiceReportResponse
from api.services.voice import transcribe

router = APIRouter(prefix="/voice-report", tags=["voice"])


@router.post("/transcribe", response_model=VoiceReportResponse)
async def transcribe_voice_report(body: VoiceReportCreate):
    """Transcribe audio; the user submits the complete report separately."""
    transcript = await transcribe(
        body.audio_base64,
        language_hint=body.language_hint,
    )

    if transcript.error and not transcript.original_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Transcription failed: {transcript.error}",
        )

    return VoiceReportResponse(
        original_text=transcript.original_text,
        detected_language=transcript.detected_language,
        language_name=transcript.language_name,
        english_text=transcript.english_text,
        transcription_confidence=transcript.confidence,
    )
