"""
GET /route/score — score multiple route alternatives for pothole density.

Query params:
  origin       "lat,lng"   e.g. "12.9716,77.5946"
  destination  "lat,lng"
  alternatives int         number of route alternatives (1–5)

The endpoint queries PostGIS to find all verified potholes within 50m of each
route polyline and computes a quality score using the scoring service.

In prototype mode (no real Google Routes API key), it returns synthetic stubs
for the route geometry so the scoring logic is fully exercisable.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.schemas import RouteScore, RouteScoreResponse, WorstSegment
from api.services.scoring import PotholeEntry, compute_road_quality_score, score_to_label

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/route", tags=["route"])


# ── Stub route generator (used when Google Routes API key is absent) ───────────

# Lateral offsets (in degrees, ~100–500m) applied to each alternative's
# mid-waypoint so each route passes through a different part of the city
# and hits a different slice of the pothole database.
_ROUTE_OFFSETS = [
    (0.000,  0.000),   # Route 1 — direct line (baseline)
    (0.008,  0.005),   # Route 2 — slight north-east detour
    (-0.006, 0.010),   # Route 3 — south-east bypass
    (0.015, -0.004),   # Route 4 — northern arc
    (-0.012, -0.008),  # Route 5 — southern loop
]

# Distance/ETA deltas per route (longer routes = more road, different density)
_ROUTE_DELTAS = [
    (0.0,  0.0),
    (1.4,  4.0),
    (2.1,  6.0),
    (3.3,  9.0),
    (4.5, 12.0),
]


def _stub_routes(origin: tuple, destination: tuple, n: int) -> List[dict]:
    """
    Returns n synthetic route stubs, each using a different mid-point offset
    so they cross different areas of the city and pick up different pothole
    densities from the database — producing meaningfully distinct quality scores.
    """
    base_dist = 8.2
    base_eta  = 22.0
    mid_lat   = (origin[0] + destination[0]) / 2
    mid_lng   = (origin[1] + destination[1]) / 2
    routes    = []
    for i in range(n):
        dlat, dlng       = _ROUTE_OFFSETS[i]
        ddist, deta      = _ROUTE_DELTAS[i]
        wp_lat = mid_lat + dlat
        wp_lng = mid_lng + dlng
        routes.append(
            {
                "route_id":    f"r{i + 1}",
                "polyline":    f"stub_polyline_{i + 1}",
                "distance_km": round(base_dist + ddist, 1),
                "eta_minutes": round(base_eta  + deta,  1),
                # Three-point WKT so each route passes through a distinct waypoint
                "wkt": (
                    f"LINESTRING("
                    f"{origin[1]} {origin[0]}, "
                    f"{wp_lng} {wp_lat}, "
                    f"{destination[1]} {destination[0]})"
                ),
            }
        )
    return routes


# ── PostGIS: potholes along a route ───────────────────────────────────────────

async def _potholes_on_route(wkt: str, db: AsyncSession) -> List[dict]:
    """
    Return verified potholes within 50m of the given WKT linestring.
    """
    sql = text(
        """
        SELECT
            p.severity,
            p.ml_confidence,
            p.reported_at,
            rs.name          AS segment_name,
            rs.quality_score AS segment_score,
            ST_Y(p.location::geometry) AS lat,
            ST_X(p.location::geometry) AS lng
        FROM pothole_report p
        LEFT JOIN road_segments rs ON rs.id = p.road_segment_id
        WHERE ST_DWithin(
            p.location,
            ST_GeographyFromText(:wkt),
            50
        )
          AND p.status = 'verified'
        ORDER BY p.reported_at DESC
        """
    )
    result = await db.execute(sql, {"wkt": wkt})
    return [dict(row._mapping) for row in result.fetchall()]


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
        olat, olng = (float(x) for x in origin.split(","))
        dlat, dlng = (float(x) for x in destination.split(","))
    except ValueError:
        raise HTTPException(status_code=422, detail="origin/destination must be 'lat,lng'")

    raw_routes = _stub_routes((olat, olng), (dlat, dlng), alternatives)

    scored: List[RouteScore] = []
    from datetime import timezone

    for idx, route in enumerate(raw_routes):
        potholes_data = await _potholes_on_route(route["wkt"], db)

        entries = [
            PotholeEntry(
                severity=p["severity"] or "low",
                reported_at=p["reported_at"].replace(tzinfo=timezone.utc)
                if p["reported_at"].tzinfo is None
                else p["reported_at"],
                ml_confidence=p["ml_confidence"] or 1.0,
            )
            for p in potholes_data
        ]

        # Use the actual route distance so density (potholes/km) is normalised
        # correctly — a short route with 2 potholes scores worse than a long one.
        score = compute_road_quality_score(entries, segment_length_km=route["distance_km"])
        label = score_to_label(score)

        # Find the worst segment (lowest quality_score) along this route
        worst: Optional[WorstSegment] = None
        segments_with_score = [
            p for p in potholes_data if p.get("segment_score") is not None
        ]
        if segments_with_score:
            worst_p = min(segments_with_score, key=lambda x: x["segment_score"])
            worst = WorstSegment(
                name=worst_p.get("segment_name") or "Unknown road",
                score=worst_p["segment_score"],
                lat=worst_p["lat"],
                lng=worst_p["lng"],
            )

        scored.append(
            RouteScore(
                route_id=route["route_id"],
                polyline=route["polyline"],
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
