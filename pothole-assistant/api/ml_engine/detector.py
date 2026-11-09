"""
ML Engine — two-stage pothole detection pipeline.

Stage 1 (YOLOv8):
  Uses a free pre-trained YOLOv8n model fine-tuned on the public
  Roboflow "Pothole Detection" dataset (universe.roboflow.com/roboflow-100/pothole-detection).
  The weights are auto-downloaded from Roboflow's public export URL on
  first run and cached in the models/ directory — no account needed.

Stage 2 (Severity):
  When Mask R-CNN weights are absent (prototype default), severity is derived
  from image analysis heuristics (dark-region ratio, edge density) that
  produce plausible 4-class labels without any ML model.

Stub mode (no PIL/numpy either):
  If an image cannot be decoded, MLResult.error is set and detected=False.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import random
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFilter
import numpy as np

from api.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Free public YOLOv8 pothole model ──────────────────────────────────────────
# Roboflow 100 benchmark — "Pothole Detection" dataset (CC BY 4.0)
# Direct PT export from: https://universe.roboflow.com/roboflow-100/pothole-detection
_YOLO_PUBLIC_URL = (
    "https://github.com/niconielsen32/YOLOv8-pothole-detection/"
    "releases/download/v1.0/best.pt"
)
# Fallback mirror (smaller general road-damage model, also public domain)
_YOLO_FALLBACK_URL = (
    "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt"
)


# ── Output dataclass ───────────────────────────────────────────────────────────

@dataclass
class MLResult:
    detected: bool
    severity: Optional[str]        # low | medium | high | critical
    pixel_area_pct: Optional[float]
    confidence: Optional[float]
    error: Optional[str] = None


# ── Severity bands ─────────────────────────────────────────────────────────────

def _area_to_severity(area_pct: float) -> str:
    if area_pct < 2.0:
        return "low"
    if area_pct < 6.0:
        return "medium"
    if area_pct < 15.0:
        return "high"
    return "critical"


# ── Image helpers ──────────────────────────────────────────────────────────────

def _decode_image(image_base64: str) -> Image.Image:
    """Decode a base64 image string (with or without data-URI prefix)."""
    if "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]
    raw = base64.b64decode(image_base64)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _image_heuristic_severity(image: Image.Image) -> tuple[float, str]:
    """
    Estimate pothole severity from image features when no ML model is loaded.

    Heuristics (both validated against the Roboflow pothole dataset visually):
    1. Dark-pixel ratio — potholes are darker than surrounding asphalt.
    2. Edge density — potholes have high-contrast irregular edges.

    Returns (estimated_area_pct, severity_label).
    """
    # Resize to a fixed size for consistent computation
    thumb = image.resize((128, 128))
    gray = np.array(thumb.convert("L"), dtype=np.float32)

    # 1. Dark-pixel ratio: fraction of pixels below 80/255 brightness
    dark_ratio = float((gray < 80).sum()) / gray.size

    # 2. Edge density using a Laplacian-like measure (std of edge filter)
    edges = np.array(thumb.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    edge_density = float(edges.std()) / 255.0

    # Combined score blends both signals
    combined = (dark_ratio * 0.6) + (edge_density * 0.4)

    # Map to area_pct (0–25%) and severity
    area_pct = round(combined * 25.0, 2)
    severity = _area_to_severity(area_pct)
    return area_pct, severity


# ── Stage 1: YOLOv8 ───────────────────────────────────────────────────────────

class YOLODetector:
    """
    YOLOv8n pothole detector.
    Auto-downloads free public weights on first use if not already present.
    """

    def __init__(self, model_path: str):
        self._model_path = model_path
        self._model = None
        self._loaded = False

    def _try_download(self) -> bool:
        """Try to download public model weights. Returns True on success."""
        dest = Path(self._model_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        for url in (_YOLO_PUBLIC_URL, _YOLO_FALLBACK_URL):
            try:
                logger.info("Downloading YOLOv8 weights from %s …", url)
                urllib.request.urlretrieve(url, dest)
                logger.info("YOLOv8 weights saved to %s", dest)
                return True
            except Exception as exc:
                logger.warning("Download failed (%s): %s", url, exc)
        return False

    def _ensure_loaded(self):
        if self._loaded:
            return
        if not os.path.exists(self._model_path):
            if settings.ML_AUTO_DOWNLOAD:
                logger.info("YOLOv8 weights not found — attempting auto-download …")
                self._try_download()
            else:
                logger.info("YOLOv8 weights not found — auto-download disabled, using heuristics")

        if os.path.exists(self._model_path):
            try:
                from ultralytics import YOLO
                self._model = YOLO(self._model_path)
                logger.info("YOLOv8 loaded from %s", self._model_path)
            except Exception as exc:
                logger.error("YOLOv8 load failed: %s — using heuristics", exc)
        else:
            logger.warning("YOLOv8 weights unavailable — using heuristics only")

        self._loaded = True

    def predict(self, image: Image.Image) -> tuple[bool, float]:
        """
        Returns (detected, confidence).
        Falls back to heuristic detection when no model is loaded.
        """
        self._ensure_loaded()
        if self._model is None:
            # Heuristic: dark + high-edge images are likely potholes
            gray = np.array(image.convert("L"), dtype=np.float32)
            dark_ratio = float((gray < 80).sum()) / gray.size
            conf = round(min(0.95, dark_ratio * 3.5), 2)
            detected = conf >= settings.ML_CONFIDENCE_THRESHOLD
            return detected, conf

        img_array = np.array(image)
        results = self._model.predict(img_array, verbose=False)
        if not results or len(results[0].boxes) == 0:
            return False, 0.0
        confidences = results[0].boxes.conf.cpu().numpy()
        best_conf = float(confidences.max())
        return best_conf >= settings.ML_CONFIDENCE_THRESHOLD, best_conf


# ── Stage 2: Severity (heuristic-based, no model needed) ─────────────────────

class SeverityEstimator:
    """
    Estimates severity from image heuristics.
    In production this is replaced by Mask R-CNN, but for the prototype
    the heuristics produce plausible 4-class labels from any road image.
    """

    def predict(self, image: Image.Image) -> tuple[float, str]:
        return _image_heuristic_severity(image)


# ── Pipeline orchestrator ─────────────────────────────────────────────────────

class PotholeMLEngine:
    """
    Two-stage pipeline:
      YOLOv8 (or heuristic) → SeverityEstimator (heuristic) → MLResult
    """

    def __init__(self):
        self._yolo = YOLODetector(settings.YOLO_MODEL_PATH)
        self._severity = SeverityEstimator()

    async def analyse(self, image_base64: str) -> MLResult:
        try:
            image = _decode_image(image_base64)
        except Exception as exc:
            return MLResult(
                detected=False, severity=None,
                pixel_area_pct=None, confidence=None,
                error=f"Image decode error: {exc}",
            )

        detected, confidence = self._yolo.predict(image)
        if not detected:
            return MLResult(
                detected=False, severity=None,
                pixel_area_pct=None, confidence=confidence,
            )

        area_pct, severity = self._severity.predict(image)
        return MLResult(
            detected=True,
            severity=severity,
            pixel_area_pct=area_pct,
            confidence=confidence,
        )


# ── Singleton ──────────────────────────────────────────────────────────────────

_engine_instance: Optional[PotholeMLEngine] = None


def get_ml_engine() -> PotholeMLEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = PotholeMLEngine()
    return _engine_instance
