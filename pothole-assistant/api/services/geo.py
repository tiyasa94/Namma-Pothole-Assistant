"""
H3 geospatial utilities.

- Converts lat/lng to H3 cell index at a given resolution.
- Builds GeoJSON for heatmap hexagons from DB rows.
- Resolution 9 (~174m edge) is the default for pothole density tracking.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    import h3
    H3_AVAILABLE = True
except ImportError:
    H3_AVAILABLE = False


DEFAULT_RESOLUTION = 9  # H3 resolution used across the system


# ── h3 version compatibility ──────────────────────────────────────────────────
# h3-py v3.x uses geo_to_h3 / h3_to_geo_boundary
# h3-py v4.x uses latlng_to_cell / cell_to_boundary
if H3_AVAILABLE:
    if hasattr(h3, "latlng_to_cell"):
        _h3_encode = h3.latlng_to_cell          # v4
        _h3_boundary = h3.cell_to_boundary      # v4
    else:
        _h3_encode = h3.geo_to_h3               # v3
        _h3_boundary = h3.h3_to_geo_boundary    # v3


def lat_lng_to_h3(lat: float, lng: float, resolution: int = DEFAULT_RESOLUTION) -> Optional[str]:
    """
    Return the H3 cell index for a given lat/lng at the specified resolution.
    Returns None if the h3 library is not installed (for test environments).
    """
    if not H3_AVAILABLE:
        # Deterministic stub for testing without the h3 library
        return f"stub_{lat:.4f}_{lng:.4f}_r{resolution}"
    return _h3_encode(lat, lng, resolution)


def h3_to_geojson_polygon(h3_index: str) -> Dict[str, Any]:
    """Return a GeoJSON Polygon geometry for an H3 cell boundary."""
    if not H3_AVAILABLE:
        return {"type": "Polygon", "coordinates": [[]]}
    boundary = _h3_boundary(h3_index)
    # h3 returns (lat, lng) tuples; GeoJSON needs [lng, lat]
    coords = [[lng, lat] for lat, lng in boundary]
    coords.append(coords[0])  # close the ring
    return {"type": "Polygon", "coordinates": [coords]}


def build_heatmap_geojson(
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a GeoJSON FeatureCollection from a list of DB rows.

    Each row must have:
      h3_index_r9: str
      quality_score: float
      pothole_count: int
    """
    features = []
    for row in rows:
        h3_cell = row["h3_index_r9"]
        features.append(
            {
                "type": "Feature",
                "geometry": h3_to_geojson_polygon(h3_cell),
                "properties": {
                    "h3_cell": h3_cell,
                    "quality_score": row.get("quality_score", 100.0),
                    "pothole_count": row.get("pothole_count", 0),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
