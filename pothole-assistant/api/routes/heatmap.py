"""
GET /heatmap — return H3 hexagon density data for map rendering.

Query params:
  bbox        "south,west,north,east"  e.g. "12.85,77.48,13.10,77.75"
  resolution  int 7–12 (default 9)

Returns a GeoJSON FeatureCollection of H3 hexagons with quality_score
and pothole_count properties — consumed directly by Deck.gl H3HexagonLayer.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.schemas import HeatmapResponse
from api.services.geo import build_heatmap_geojson

router = APIRouter(prefix="/heatmap", tags=["heatmap"])


@router.get("/", response_model=HeatmapResponse)
async def get_heatmap(
    bbox: str = Query(..., description="south,west,north,east e.g. 12.85,77.48,13.10,77.75"),
    resolution: int = Query(9, ge=7, le=12),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregate verified pothole reports into H3 hex cells and return
    GeoJSON for heatmap rendering.
    """
    try:
        south, west, north, east = (float(x) for x in bbox.split(","))
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="bbox must be 'south,west,north,east'")

    # Aggregate pothole density per H3 cell within the requested bounding box
    sql = text(
        """
        SELECT
            p.h3_index_r9,
            COUNT(*)                           AS pothole_count,
            AVG(rs.quality_score)              AS quality_score
        FROM pothole_report p
        LEFT JOIN road_segments rs ON rs.id = p.road_segment_id
        WHERE
            p.status = 'verified'
            AND ST_Within(
                p.location::geometry,
                ST_MakeEnvelope(:west, :south, :east, :north, 4326)
            )
            AND p.h3_index_r9 IS NOT NULL
        GROUP BY p.h3_index_r9
        ORDER BY pothole_count DESC
        """
    )
    result = await db.execute(
        sql, {"south": south, "west": west, "north": north, "east": east}
    )
    rows = [dict(r._mapping) for r in result.fetchall()]

    # Fill in a default quality score for cells with no segment match
    for row in rows:
        if row["quality_score"] is None:
            row["quality_score"] = 50.0  # unknown — render as Fair

    geojson = build_heatmap_geojson(rows)
    return geojson
