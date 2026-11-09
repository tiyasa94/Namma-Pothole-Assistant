"""
FastAPI application entry point.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.config import get_settings
from api.routes import heatmap, maintenance, reports, route_score, voice_report

settings = get_settings()

app = FastAPI(
    title="Bengaluru Pothole Assistant API",
    description=(
        "Backend for citizen pothole reporting, ML-based severity detection, "
        "road quality scoring, and BBMP maintenance logging."
    ),
    version="0.1.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(reports.router,      prefix="/v1")
app.include_router(route_score.router,  prefix="/v1")
app.include_router(maintenance.router,  prefix="/v1")
app.include_router(heatmap.router,      prefix="/v1")
app.include_router(voice_report.router, prefix="/v1")


# ── Static file serving for local image uploads ───────────────────────────────
_uploads_dir = Path(settings.LOCAL_STORAGE_PATH)
_uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok"}
