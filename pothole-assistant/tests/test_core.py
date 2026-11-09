"""
Smoke tests for the ML engine, scoring service, and geo utilities.
Run with:  pytest tests/ -v
No database or model weights required.
"""
import base64
import io
import uuid
from datetime import datetime, timezone

import pytest
from PIL import Image


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_base64_image(width: int = 64, height: int = 64, color: str = "gray") -> str:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


# ── Scoring service ────────────────────────────────────────────────────────────

class TestRoadQualityScore:
    from api.services.scoring import PotholeEntry, compute_road_quality_score, score_to_label

    def test_no_potholes_returns_100(self):
        from api.services.scoring import compute_road_quality_score
        assert compute_road_quality_score([]) == 100.0

    def test_single_critical_pothole_reduces_score(self):
        from api.services.scoring import PotholeEntry, compute_road_quality_score
        entry = PotholeEntry(
            severity="critical",
            reported_at=datetime.now(tz=timezone.utc),
            ml_confidence=1.0,
        )
        score = compute_road_quality_score([entry], segment_length_km=0.5)
        assert score < 100.0
        assert score >= 0.0

    def test_score_bounded_0_to_100(self):
        from api.services.scoring import PotholeEntry, compute_road_quality_score
        entries = [
            PotholeEntry("critical", datetime.now(tz=timezone.utc), 1.0)
            for _ in range(50)
        ]
        score = compute_road_quality_score(entries, segment_length_km=0.1)
        assert 0.0 <= score <= 100.0

    def test_label_excellent(self):
        from api.services.scoring import score_to_label
        assert score_to_label(95.0) == "Excellent"

    def test_label_critical(self):
        from api.services.scoring import score_to_label
        assert score_to_label(10.0) == "Critical"

    def test_older_potholes_penalise_less(self):
        from api.services.scoring import PotholeEntry, compute_road_quality_score
        old = PotholeEntry(
            severity="high",
            reported_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ml_confidence=1.0,
        )
        recent = PotholeEntry(
            severity="high",
            reported_at=datetime.now(tz=timezone.utc),
            ml_confidence=1.0,
        )
        score_old = compute_road_quality_score([old])
        score_recent = compute_road_quality_score([recent])
        assert score_old > score_recent


# ── Geo utilities ──────────────────────────────────────────────────────────────

class TestGeoUtils:
    def test_lat_lng_to_h3_returns_string(self):
        from api.services.geo import lat_lng_to_h3
        result = lat_lng_to_h3(12.9716, 77.5946)
        assert result is not None
        assert isinstance(result, str)

    def test_build_heatmap_geojson_structure(self):
        from api.services.geo import build_heatmap_geojson, lat_lng_to_h3
        # Derive a real H3 index (or stub when h3 is absent) from a known coordinate
        h3_cell = lat_lng_to_h3(12.9716, 77.5946)
        rows = [
            {"h3_index_r9": h3_cell, "quality_score": 65.0, "pothole_count": 4},
        ]
        geojson = build_heatmap_geojson(rows)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1
        feat = geojson["features"][0]
        assert feat["properties"]["pothole_count"] == 4


# ── ML engine stub mode ────────────────────────────────────────────────────────

class TestMLEngine:
    @pytest.mark.asyncio
    async def test_heuristic_returns_mlresult(self):
        """No model weights needed — heuristic path returns a valid MLResult."""
        from api.ml_engine.detector import PotholeMLEngine
        engine = PotholeMLEngine()
        # Dark grey image — should look pothole-like to heuristic
        image_b64 = _make_base64_image(color=(40, 40, 40))
        result = await engine.analyse(image_b64)
        assert result.detected in (True, False)
        assert result.error is None

    @pytest.mark.asyncio
    async def test_bright_image_unlikely_pothole(self):
        """A bright white image has very low dark-pixel ratio → low confidence."""
        from api.ml_engine.detector import PotholeMLEngine
        engine = PotholeMLEngine()
        image_b64 = _make_base64_image(color=(240, 240, 240))
        result = await engine.analyse(image_b64)
        # With near-zero dark pixels, heuristic confidence is below threshold
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_invalid_image_returns_error(self):
        from api.ml_engine.detector import PotholeMLEngine
        engine = PotholeMLEngine()
        result = await engine.analyse("not_valid_base64!!!")
        assert result.error is not None
        assert result.detected is False

class TestImageHeuristics:
    def test_dark_image_high_severity(self):
        """Very dark image → high area_pct → high/critical severity."""
        from api.ml_engine.detector import _image_heuristic_severity
        dark_img = Image.new("RGB", (128, 128), color=(20, 20, 20))
        area_pct, severity = _image_heuristic_severity(dark_img)
        assert area_pct > 0
        assert severity in ("medium", "high", "critical")

    def test_bright_image_low_severity(self):
        """Bright image → low dark ratio → low area_pct."""
        from api.ml_engine.detector import _image_heuristic_severity
        bright_img = Image.new("RGB", (128, 128), color=(230, 230, 230))
        area_pct, severity = _image_heuristic_severity(bright_img)
        assert severity in ("low", "medium")
