"""
Central configuration — all values are read from environment variables.
Use .env.example as a template and copy to .env before running.
"""
from functools import lru_cache
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://pothole:pothole@localhost:5432/potholedb"

    # ── Local image storage (replaces GCS for prototype) ─────────────────────
    LOCAL_STORAGE_PATH: str = "uploads"

    # ── ML Engine ─────────────────────────────────────────────────────────────
    # Weights are auto-downloaded from a free public repo on first run.
    # Set to a local path to use your own fine-tuned weights.
    YOLO_MODEL_PATH: str = "models/yolov8n_pothole.pt"
    MASKRCNN_MODEL_PATH: str = "models/maskrcnn_pothole.pth"  # unused in prototype
    ML_CONFIDENCE_THRESHOLD: float = 0.50
    # Set to false to disable auto-download (useful in CI / tests)
    ML_AUTO_DOWNLOAD: bool = True

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"  # development | production
    SECRET_KEY: str = "change-me-in-production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
