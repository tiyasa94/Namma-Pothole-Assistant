"""
Local filesystem image storage — prototype replacement for GCS.

Images are saved to LOCAL_STORAGE_PATH (default: ./uploads/) and served
via a static-files mount on the API.  No cloud account needed.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
from pathlib import Path

from PIL import Image

from api.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _storage_dir() -> Path:
    path = Path(settings.LOCAL_STORAGE_PATH)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_image_base64(image_base64: str, report_id: str) -> str:
    """
    Decode a base64 image, save it locally, and return a relative URL path.
    Returns the URL path e.g. "/uploads/<hash>.jpg".
    Duplicate images (same hash) are de-duplicated automatically.
    """
    if "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]

    # Add padding if missing (common when base64 is URL-encoded or trimmed)
    image_base64 += "=" * (-len(image_base64) % 4)

    raw = base64.b64decode(image_base64)

    # Use SHA-1 of raw bytes as filename — deduplicates identical uploads
    sha = hashlib.sha1(raw).hexdigest()
    filename = f"{sha}.jpg"
    dest = _storage_dir() / filename

    if not dest.exists():
        # Re-encode as JPEG to normalise format and strip EXIF metadata
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.save(dest, format="JPEG", quality=85)
        logger.debug("Saved image %s (%d bytes)", filename, dest.stat().st_size)

    return f"/uploads/{filename}"


def save_image_from_url(url: str, filename: str) -> str:
    """
    Download an image from a public URL and save it locally.
    Used by the seed script to cache public dataset images.
    Returns the relative URL path.
    """
    import urllib.request

    dest = _storage_dir() / filename
    if not dest.exists():
        urllib.request.urlretrieve(url, dest)
        logger.debug("Downloaded %s → %s", url, dest)
    return f"/uploads/{filename}"
