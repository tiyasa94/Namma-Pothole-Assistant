"""
Pydantic request/response schemas for all API endpoints.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ── POST /reports ──────────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="WGS84 latitude")
    lng: float = Field(..., ge=-180, le=180, description="WGS84 longitude")
    image_base64: Optional[str] = Field(
        default=None,
        description="Base64-encoded JPEG/PNG image. Omit if no photo available.",
        json_schema_extra={"example": None},
    )
    severity_hint: Optional[str] = Field(
        default=None,
        description="User's perceived severity: low | medium | high | critical",
        json_schema_extra={"example": None},
    )
    description: Optional[str] = Field(default=None, max_length=500)
    source: str = Field("photo", description="photo | voice | passive_sensor")


class ReportResponse(BaseModel):
    report_id: uuid.UUID
    status: str
    h3_cell: Optional[str]
    road_segment_id: Optional[uuid.UUID]
    estimated_verification_time_seconds: int = 30


# ── GET /route/score ───────────────────────────────────────────────────────────

class WorstSegment(BaseModel):
    name: str
    score: float
    lat: float
    lng: float


class RouteScore(BaseModel):
    route_id: str
    polyline: str
    distance_km: float
    eta_minutes: float
    quality_score: float
    quality_label: str
    hotspot_count: int
    worst_segment: Optional[WorstSegment]


class RouteScoreResponse(BaseModel):
    routes: List[RouteScore]


# ── POST /maintenance ──────────────────────────────────────────────────────────

class BboxCoord(BaseModel):
    lat: float
    lng: float


class MaintenanceCreate(BaseModel):
    road_segment_id: uuid.UUID
    work_type: str = Field(..., description="repair | utility_dig | resurfacing | patching")
    status: str = Field("planned", description="planned | in_progress | completed")
    affected_bbox: Optional[List[List[float]]] = Field(
        None, description="[[lat,lng],[lat,lng]] bounding box corners"
    )
    notes: Optional[str] = None


class MaintenanceResponse(BaseModel):
    maintenance_id: uuid.UUID
    status: str


# ── POST /voice-report ────────────────────────────────────────────────────────

class VoiceReportCreate(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="WGS84 latitude")
    lng: float = Field(..., ge=-180, le=180, description="WGS84 longitude")
    audio_base64: str = Field(
        ...,
        description="Base64-encoded WAV/MP3/OGG audio (max ~10MB). "
                    "The speaker can use English, Hindi, or Kannada.",
    )
    language_hint: Optional[str] = Field(
        default=None,
        description="Optional language hint: 'en', 'hi', or 'kn'. "
                    "If omitted, all three languages are tried automatically.",
        json_schema_extra={"example": None},
    )


class VoiceReportResponse(BaseModel):
    report_id: uuid.UUID
    status: str
    h3_cell: Optional[str]
    road_segment_id: Optional[uuid.UUID]
    original_text: str               # transcribed in detected language
    detected_language: str           # "en" | "hi" | "kn"
    language_name: str               # "English" | "Hindi" | "Kannada"
    english_text: str                # always English
    transcription_confidence: float
    estimated_verification_time_seconds: int = 30


# ── GET /heatmap ───────────────────────────────────────────────────────────────

class HeatmapFeatureProps(BaseModel):
    h3_cell: str
    quality_score: float
    pothole_count: int


class HeatmapFeature(BaseModel):
    type: str = "Feature"
    geometry: dict
    properties: HeatmapFeatureProps


class HeatmapResponse(BaseModel):
    type: str = "FeatureCollection"
    features: List[HeatmapFeature]
