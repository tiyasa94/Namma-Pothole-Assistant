"""
pytest configuration — set environment overrides before any module import.
"""
import os

# Disable YOLOv8 auto-download during tests — avoids network calls and hangs.
os.environ["ML_AUTO_DOWNLOAD"] = "false"

# Clear the settings lru_cache so the env override above takes effect
# (the cache may have been populated by an earlier import in this process).
try:
    from api.config import get_settings
    get_settings.cache_clear()
except Exception:
    pass
