# 🛣️ Namma Pothole Assistant

> **Bengaluru's community-powered, AI-driven road intelligence platform.**  
> Report potholes in seconds. Choose the safest route before you leave home.  
> Give BBMP officers a real-time repair dashboard — no spreadsheets, no guesswork.

Built for the **IBM Bob Hackathon · Smarter Streets, Better Living** track.

---

## The problem in one sentence

Google Maps routes Bengaluru commuters by speed — not by road quality.  
Every monsoon, ~50,000 potholes appear across the city. Residents have no way to know which roads are dangerous before they hit them. BBMP officers have no unified, AI-verified data to prioritise repairs.

---

## What this app does

| Feature | How it works |
|---|---|
| **📍 Pothole reporting** | Pin location, upload a required photo, choose severity, and type or dictate a description (English / Hindi / Kannada) |
| **🤖 AI verification** | YOLOv8 object detection auto-confirms the pothole; heuristic severity estimator classifies it as low / medium / high / critical |
| **📊 Road Quality Score** | Each road segment gets a 0–100 score computed from severity, pothole density, and report recency — updates automatically after every verified report |
| **🗺️ Route Planner** | Score up to 5 route alternatives between any two Bengaluru points; sorted best-first with worst stretch highlighted |
| **🔥 BBMP Heatmap** | H3 hexagonal heatmap of all verified reports across Bengaluru — colour-coded Critical → Excellent |
| **🔧 Maintenance logger** | BBMP officers log repair work orders; marking a road **completed** instantly refreshes the quality score for commuters |

---

## Live demo walkthrough

### Citizen flow
1. Open the **🧑 Citizen — Report & Navigate** tab.
2. Click the map near any Bengaluru location to move the pin.
3. Upload the required pothole photo (JPEG/PNG).
4. Type the description or record a voice note to transcribe it into the description field; then choose a severity.
5. Hit **🚀 Submit Pothole Report**. A photo, description, and severity are required. Instant confirmation: `report_id` + H3 cell.
6. Hit **🔄 Check ML Status** — severity badge, confidence %, and pixel area appear.
7. Switch to **🗺️ Route Planner** → pick a preset route → **🔍 Score My Route** → see routes ranked, best first.

### BBMP officer flow
1. Open the **🏛️ BBMP Officer — Monitor & Maintain** tab.
2. **Hotspot Heatmap** — dark red hexagons = send the crew here first.
3. Click a hexagon popup: score / report count / H3 cell ID.
4. **Log Maintenance** — fill work type, status, affected bounding box → **📋 Log Work Order**.
5. Change status to `completed` → 🎉 road quality score recalculates; commuters see the improvement immediately.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│              Streamlit UI  (two-persona app)             │
│   🧑 Citizen: Report · Route Planner · Voice            │
│   🏛️ BBMP:   Heatmap · Maintenance Logger               │
└─────────────────┬────────────────────────────────────────┘
                  │ HTTP
┌─────────────────▼────────────────────────────────────────┐
│           FastAPI Backend  (api/main.py)                 │
│  POST /v1/reports   GET /v1/route/score                  │
│  GET  /v1/heatmap   POST /v1/maintenance                 │
│  POST /v1/voice-report/transcribe                        │
└────┬──────────────┬──────────────────┬───────────────────┘
     │              │                  │
┌────▼─────┐  ┌─────▼──────┐  ┌───────▼──────┐
│ ML Engine│  │  Scoring   │  │ Voice / ASR  │
│ YOLOv8   │  │  Engine    │  │ Bhashini /   │
│ + heuris-│  │ (PostGIS   │  │ Google Speech│
│ tic sev. │  │  + H3)     │  │              │
└────┬─────┘  └─────┬──────┘  └──────────────┘
     └──────────────┴─────────────────────────
                    │
┌───────────────────▼──────────────────────────────────────┐
│      PostgreSQL 15 + PostGIS 3.4  (spatial database)     │
│  pothole_report · road_segments · maintenance_log        │
└──────────────────────────────────────────────────────────┘
```

### Tech stack

| Layer | Technology |
|---|---|
| UI | Streamlit + Folium + streamlit-folium |
| API | FastAPI + Uvicorn (async) |
| ML | YOLOv8 (public pothole weights, CC BY 4.0) + PIL heuristics |
| Spatial DB | PostgreSQL 15 + PostGIS 3.4 |
| Spatial index | Uber H3 hexagonal grid |
| ORM | SQLAlchemy 2 (async) + GeoAlchemy2 |
| Voice | Google Speech Recognition with local faster-whisper fallback + deep-translator + langdetect |
| Containerisation | Docker + Docker Compose |

If Google Speech Recognition cannot identify a recording, the API falls back to
the multilingual faster-whisper `base` model on CPU. The model is downloaded on
the first fallback transcription and cached inside the API container.

---

## Agentic AI — the loop that runs without you

The system is **agentic**: it perceives inputs, reasons about them, and acts on world state — without a human triggering each step.

```
Citizen submits photo
  → API returns 201 instantly          ← non-blocking
  → Background ML agent fires:
      decode image
      → YOLOv8 detects pothole
      → heuristic estimates severity (low / medium / high / critical)
      → patch DB row: status = verified
      → recompute Road Quality Score for linked road segment
      → Route Planner now reflects new reality
                                        ← zero further human input
```

**Road Quality Score formula** (`api/services/scoring.py`):

```
Score = 100 − min(100, Severity_Penalty + Concentration_Penalty + Recency_Penalty)
```

| Penalty | What it captures | Cap |
|---|---|---|
| Severity | Weighted sum of severity × ML confidence ÷ segment length (km) | 40 pts |
| Concentration | Pothole density per km × 3 | 30 pts |
| Recency | Exponential decay — half-life 90 days; fresh potholes hurt more | 30 pts |

Score bands: `Critical 0–34` · `Poor 35–54` · `Fair 55–74` · `Good 75–89` · `Excellent 90–100`

---

## Getting started

### Prerequisites

- Python 3.11+
- Docker Desktop (recommended) **or** PostgreSQL 15 + PostGIS extension installed locally

### Option A — Docker Compose (recommended, one command)

```bash
git clone https://github.com/your-org/bobathon.git
cd bobathon/pothole-assistant

cp .env.example .env          # defaults work out of the box

docker compose up --build
```

If you already have a PostgreSQL Docker volume from an earlier version, init
scripts do not run again automatically. Apply the new report-severity column once:

```bash
docker compose exec -T db psql -U pothole -d potholedb \
  -c "ALTER TABLE pothole_report ADD COLUMN IF NOT EXISTS user_severity_hint VARCHAR(10) CHECK (user_severity_hint IN ('low', 'medium', 'high', 'critical'));"
```

| Service | URL |
|---|---|
| FastAPI + Swagger UI | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| pgAdmin *(optional)* | `docker compose --profile debug up` → http://localhost:5050 |

Then in a second terminal:

```bash
# Seed 300 synthetic Bengaluru pothole reports for the demo heatmap
python scripts/seed_data.py --generate --clear

# Start the Streamlit UI
streamlit run streamlit_app.py
# → http://localhost:8501
```

---

### Option B — bare Python (no Docker)

```bash
# 1. Clone & create virtualenv
git clone https://github.com/your-org/bobathon.git
cd bobathon/pothole-assistant
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# Optional: real YOLOv8 inference (pulls ~2 GB torch)
pip install ultralytics --extra-index-url https://download.pytorch.org/whl/cpu

# 3. Configure
cp .env.example .env
# Edit .env → set DATABASE_URL to your local PostGIS instance

# 4. Run DB migrations (first time only)
psql -U pothole -d potholedb -f db/migrations/001_initial.sql

# 5. Seed demo data
python scripts/seed_data.py --generate --clear

# 6. Start the API
uvicorn api.main:app --reload --port 8000

# 7. Start the UI (new terminal)
streamlit run streamlit_app.py
```

---

### Environment variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://pothole:pothole@localhost:5432/potholedb` | Async PostgreSQL connection string |
| `LOCAL_STORAGE_PATH` | `uploads` | Directory for uploaded pothole images |
| `YOLO_MODEL_PATH` | `models/yolov8n_pothole.pt` | YOLOv8 weights — auto-downloaded on first run |
| `ML_CONFIDENCE_THRESHOLD` | `0.50` | Minimum confidence to mark a report verified |
| `ML_AUTO_DOWNLOAD` | `true` | Download public YOLOv8 weights automatically |
| `SECRET_KEY` | `dev-secret-change-me` | Bearer token for BBMP `/v1/maintenance` endpoint |

---

## Running tests

```bash
pytest tests/ -v
```

The test suite uses `pytest-asyncio` and an in-memory SQLite database — no live PostGIS needed.

---

## Project structure

```
bobathon/
├── SUBMISSION.md                    # Hackathon submission document
├── POTHOLE_ASSISTANT_PLAN.md        # Full technical + product plan (18 sections)
└── pothole-assistant/
    ├── api/
    │   ├── main.py                  # FastAPI app entry point
    │   ├── config.py                # Pydantic Settings (env-driven)
    │   ├── database.py              # Async SQLAlchemy engine + session
    │   ├── routes/
    │   │   ├── reports.py           # POST /v1/reports — photo report + async ML
    │   │   ├── route_score.py       # GET  /v1/route/score — route quality scoring
    │   │   ├── heatmap.py           # GET  /v1/heatmap — H3 GeoJSON heatmap
    │   │   ├── maintenance.py       # POST /v1/maintenance — BBMP work orders
    │   │   └── voice_report.py      # POST /v1/voice-report/transcribe — audio transcription
    │   ├── ml_engine/
    │   │   └── detector.py          # YOLOv8 + heuristic 2-stage ML pipeline
    │   ├── services/
    │   │   ├── scoring.py           # Road Quality Score algorithm
    │   │   ├── geo.py               # H3 indexing + PostGIS helpers
    │   │   └── voice.py             # Transcription + language detection + translation
    │   └── models/
    │       ├── orm.py               # SQLAlchemy: PotholeReport, RoadSegment, MaintenanceLog
    │       └── schemas.py           # Pydantic request/response schemas
    ├── streamlit_app.py             # Full two-persona Streamlit UI
    ├── scripts/
    │   └── seed_data.py             # Synthetic Bengaluru pothole data generator
    ├── tests/
    │   ├── conftest.py              # Async test fixtures
    │   └── test_core.py            # API + scoring unit tests
    ├── db/migrations/               # SQL migration scripts
    ├── assets/                      # Seed images
    ├── models/                      # ML weight files (auto-downloaded)
    ├── uploads/                     # Citizen-uploaded images
    ├── Dockerfile
    ├── docker-compose.yml
    ├── requirements.txt
    ├── requirements-streamlit.txt
    └── .env.example
```

---

## API reference

Interactive docs: **http://localhost:8000/docs** (Swagger UI auto-generated by FastAPI)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/v1/reports/` | — | Submit pothole report (photo + GPS) |
| `GET` | `/v1/reports/{id}` | — | Poll ML verification status |
| `GET` | `/v1/route/score` | — | Score route alternatives by road quality |
| `GET` | `/v1/heatmap` | — | H3 GeoJSON heatmap for a bounding box |
| `POST` | `/v1/maintenance/` | Bearer token | Log BBMP maintenance work order |
| `POST` | `/v1/voice-report/transcribe` | — | Transcribe a voice description for the report form |
| `GET` | `/health` | — | Health check |

---

## Built with IBM Bob

**IBM Bob (Agent mode)** was used throughout the entire development lifecycle — not just as a code generator, but as an engineering partner that read existing files, reasoned about the architecture, and made targeted changes.

| What we built | How Bob helped |
|---|---|
| System architecture + 18-section plan | Bob designed the two-sided platform, component map, and phased rollout in one session |
| Road Quality Score formula | Bob proposed the three-penalty algorithm with exponential decay; we implemented it directly |
| Async FastAPI + background ML tasks | Bob wrote the `BackgroundTasks` wiring and caught the async SQLAlchemy session-scope pitfall before runtime |
| YOLOv8 + heuristic ML pipeline | Bob designed the two-stage fallback: real YOLO when available, pixel heuristics otherwise |
| H3 geospatial engine + heatmap | Bob wrote H3 indexing, PostGIS bounding-box query, and GeoJSON builder |
| Kannada/Hindi/English voice pipeline | Bob scaffolded transcription, language detection, and translation in one pass |
| Full test suite | Bob generated pytest-asyncio stubs for all five API routes |

**Time saved:** estimated 7–9 engineer-days solo → completed in < 1.5 days with Bob in Agent mode.

