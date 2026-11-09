"""
Road Quality Score computation.

Formula (from the system plan):
  Score(S) = 100 - min(100, Severity_Penalty + Concentration_Penalty + Recency_Penalty)

Score bands:
  90–100 → Excellent
  75–89  → Good
  55–74  → Fair
  35–54  → Poor
  0–34   → Critical
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List


SEVERITY_WEIGHTS = {
    "low": 1,
    "medium": 3,
    "high": 7,
    "critical": 15,
}

SCORE_LABELS = [
    (90, "Excellent"),
    (75, "Good"),
    (55, "Fair"),
    (35, "Poor"),
    (0,  "Critical"),
]


@dataclass
class PotholeEntry:
    severity: str
    reported_at: datetime
    ml_confidence: float = 1.0


def _severity_penalty(potholes: List[PotholeEntry], segment_length_km: float) -> float:
    """
    Weighted sum of severity scores, normalised by segment length.
    Per-km penalty is capped at 40 to avoid overwhelming short segments.
    """
    raw = sum(
        SEVERITY_WEIGHTS.get(p.severity, 1) * p.ml_confidence
        for p in potholes
    )
    length = max(segment_length_km, 0.1)  # guard against zero-length segments
    return min(40.0, raw / length)


def _concentration_penalty(potholes: List[PotholeEntry], segment_length_km: float) -> float:
    """
    Density bonus: if potholes cluster tightly, the road feels worse.
    Density = count / km, scaled to 0–30.
    """
    density = len(potholes) / max(segment_length_km, 0.1)
    return min(30.0, density * 3.0)


def _recency_penalty(potholes: List[PotholeEntry]) -> float:
    """
    Recent potholes (< 30 days) add a time-based penalty up to 30 points.
    Older reports decay exponentially (half-life ≈ 90 days).
    """
    now = datetime.now(tz=timezone.utc)
    total = 0.0
    for p in potholes:
        age_days = max((now - p.reported_at).days, 0)
        decay = math.exp(-age_days / 90.0)
        total += SEVERITY_WEIGHTS.get(p.severity, 1) * decay
    return min(30.0, total)


def compute_road_quality_score(
    potholes: List[PotholeEntry],
    segment_length_km: float = 1.0,
) -> float:
    """
    Returns a road quality score in [0, 100].
    Higher is better.
    """
    if not potholes:
        return 100.0

    penalty = (
        _severity_penalty(potholes, segment_length_km)
        + _concentration_penalty(potholes, segment_length_km)
        + _recency_penalty(potholes)
    )
    return round(max(0.0, 100.0 - min(100.0, penalty)), 1)


def score_to_label(score: float) -> str:
    for threshold, label in SCORE_LABELS:
        if score >= threshold:
            return label
    return "Critical"
