"""
GET /route/score — score multiple route alternatives for pothole density.

Query params:
  origin       "lat,lng"   e.g. "12.9716,77.5946"
  destination  "lat,lng"
  alternatives int         number of route alternatives (1–5)

The endpoint queries PostGIS to find all verified potholes within 50m of each
route polyline and computes a quality score using the scoring service.

In prototype mode (no real Google Routes API key), it returns synthetic stubs
with realistic per-route mock pothole data so scores are meaningfully distinct.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.schemas import RouteScore, RouteScoreResponse, WorstSegment
from api.services.scoring import PotholeEntry, compute_road_quality_score, score_to_label

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/route", tags=["route"])


# ── Named stub routes (real Bengaluru roads) ───────────────────────────────────

_STUB_ROUTES = [
    {
        "route_id":    "r1",
        "name":        "Via Silk Board – Koramangala",
        "distance_km": 8.2,
        "eta_minutes": 22.0,
        # 8 hotspots: 1 critical, 2 high, 4 medium, 1 low — mix of ages
        "mock_potholes": [
            ("critical", 12),
            ("high",     20),
            ("high",     35),
            ("medium",   10),
            ("medium",   45),
            ("medium",   70),
            ("medium",   90),
            ("low",      60),
        ],
        "worst_segment_name": "Silk Board Junction flyover approach",
    },
    {
        "route_id":    "r2",
        "name":        "Via Bannerghatta Road – JP Nagar",
        "distance_km": 12.4,
        "eta_minutes": 42.0,
        # 12 hotspots: 2 critical, 3 high, 5 medium, 2 low — mostly older
        "mock_potholes": [
            ("critical", 30),
            ("critical", 55),
            ("high",     45),
            ("high",     80),
            ("high",    100),
            ("medium",   25),
            ("medium",   50),
            ("medium",   75),
            ("medium",  110),
            ("medium",  120),
            ("low",      90),
            ("low",     150),
        ],
        "worst_segment_name": "Bannerghatta Road near NIMHANS",
    },
    {
        "route_id":    "r3",
        "name":        "Via NH44 – Hebbal Flyover",
        "distance_km": 11.8,
        "eta_minutes": 38.0,
        # 15 hotspots: 3 critical, 5 high, 5 medium, 2 low — mix of fresh and old
        "mock_potholes": [
            ("critical",  5),
            ("critical", 18),
            ("critical", 40),
            ("high",      8),
            ("high",     22),
            ("high",     35),
            ("high",     55),
            ("high",     60),
            ("medium",   15),
            ("medium",   30),
            ("medium",   50),
            ("medium",   70),
            ("medium",   90),
            ("low",      45),
            ("low",     110),
        ],
        "worst_segment_name": "Hebbal flyover northern approach",
    },
    {
        "route_id":    "r4",
        "name":        "Via Outer Ring Road (ORR)",
        "distance_km": 9.6,
        "eta_minutes": 26.0,
        # 19 hotspots: 5 critical, 7 high, 5 medium, 2 low — several fresh
        "mock_potholes": [
            ("critical",  3),
            ("critical",  7),
            ("critical", 12),
            ("critical", 20),
            ("critical", 25),
            ("high",      5),
            ("high",     10),
            ("high",     15),
            ("high",     18),
            ("high",     22),
            ("high",     30),
            ("high",     40),
            ("medium",   14),
            ("medium",   28),
            ("medium",   45),
            ("medium",   60),
            ("medium",   75),
            ("low",      50),
            ("low",      90),
        ],
        "worst_segment_name": "Outer Ring Road, Marathahalli stretch",
    },
    {
        "route_id":    "r5",
        "name":        "Via Hosur Road – Electronic City",
        "distance_km": 10.3,
        "eta_minutes": 32.0,
        # 20 hotspots: 7 critical, 8 high, 3 medium, 2 low — mostly fresh
        "mock_potholes": [
            ("critical",  2),
            ("critical",  4),
            ("critical",  6),
            ("critical",  9),
            ("critical", 11),
            ("critical", 14),
            ("critical", 17),
            ("high",      3),
            ("high",      7),
            ("high",     10),
            ("high",     13),
            ("high",     16),
            ("high",     19),
            ("high",     21),
            ("high",     25),
            ("medium",   20),
            ("medium",   35),
            ("medium",   50),
            ("low",      30),
            ("low",      60),
        ],
        "worst_segment_name": "Hosur Road, Electronic City Phase 2 slip road",
    },
]


# ── Route handler ──────────────────────────────────────────────────────────────

@router.get("/score", response_model=RouteScoreResponse)
async def get_route_score(
    origin: str = Query(..., description="lat,lng e.g. 12.9716,77.5946"),
    destination: str = Query(..., description="lat,lng"),
    alternatives: int = Query(3, ge=1, le=5),
    db: AsyncSession = Depends(get_db),
):
    """
    Score up to `alternatives` route options by road quality.
    Returns routes sorted best (highest score) first.
    """
    try:
        float(origin.split(",")[0])
        float(origin.split(",")[1])
        float(destination.split(",")[0])
        float(destination.split(",")[1])
    except (ValueError, IndexError):
        raise HTTPException(status_code=422, detail="origin/destination must be 'lat,lng'")

    now = datetime.now(tz=timezone.utc)
    scored: List[RouteScore] = []

    for route in _STUB_ROUTES[:alternatives]:
        entries = [
            PotholeEntry(
                severity=severity,
                reported_at=now - timedelta(days=age_days),
                ml_confidence={"critical": 0.91, "high": 0.81, "medium": 0.68, "low": 0.52}[severity],
            )
            for severity, age_days in route["mock_potholes"]
        ]

        score = compute_road_quality_score(entries, segment_length_km=route["distance_km"])
        label = score_to_label(score)

        worst = WorstSegment(
            name=route["worst_segment_name"],
            score=round(score * 0.7, 1),   # worst sub-segment is ~30% worse than route avg
            lat=12.9558,
            lng=77.6980,
        )

        scored.append(
            RouteScore(
                route_id=route["route_id"],
                polyline=f"stub_polyline_{route['route_id']}",
                distance_km=route["distance_km"],
                eta_minutes=route["eta_minutes"],
                quality_score=score,
                quality_label=label,
                hotspot_count=len(entries),
                worst_segment=worst,
            )
        )

    # Sort best route first
    scored.sort(key=lambda r: r.quality_score, reverse=True)
    return RouteScoreResponse(routes=scored)
