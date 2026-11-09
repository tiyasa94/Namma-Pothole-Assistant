"""
SQLAlchemy ORM models — mirror the data models from the system plan.

All enum-like columns use plain VARCHAR to match the CHECK-constraint schema
in 001_init.sql — no PostgreSQL ENUM types are created, so the ORM works
against the existing DB without any ALTER TYPE migrations.
"""
import uuid

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from api.database import Base


# ── Tables ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(15), unique=True, nullable=False)
    preferred_lang = Column(String(2), default="en")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    total_reports = Column(Integer, default=0)
    reputation_score = Column(Float, default=1.0)


class RoadSegment(Base):
    __tablename__ = "road_segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    osm_way_id = Column(BigInteger, unique=True, nullable=True)
    name = Column(Text)
    geometry = Column(Geography(geometry_type="LINESTRING", srid=4326))
    quality_score = Column(Float, default=100.0)
    score_updated_at = Column(DateTime(timezone=True), server_default=func.now())
    pothole_count = Column(Integer, default=0)
    concentration_peak = Column(Float, default=0.0)
    under_maintenance = Column(Boolean, default=False)


class PotholeReport(Base):
    __tablename__ = "pothole_report"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location = Column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    h3_index_r9 = Column(String(15), index=True)
    image_url = Column(Text)
    severity = Column(String(10), nullable=True)        # low|medium|high|critical
    ml_confidence = Column(Float, nullable=True)
    pixel_area_pct = Column(Float, nullable=True)
    status = Column(String(20), default="pending", index=True)
    reported_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reported_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    road_segment_id = Column(UUID(as_uuid=True), ForeignKey("road_segments.id"), nullable=True)
    source = Column(String(20), default="photo")
    description = Column(Text)


class MaintenanceLog(Base):
    __tablename__ = "maintenance_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    road_segment_id = Column(UUID(as_uuid=True), ForeignKey("road_segments.id"), nullable=False)
    work_type = Column(String(20), nullable=False)
    status = Column(String(20), default="planned")
    logged_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text)
    affected_bbox = Column(Geography(geometry_type="POLYGON", srid=4326), nullable=True)
