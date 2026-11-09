# 🛣️ Bengaluru Pothole Assistant — Full System Plan

> **Document Version:** 1.0  
> **Last Updated:** November 2026  
> **Purpose:** End-to-end technical and product planning for a citizen-facing pothole reporting and intelligent route recommendation system for Bengaluru.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Product Vision & Goals](#2-product-vision--goals)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [Feature Breakdown](#4-feature-breakdown)
   - 4.1 [Citizen Pothole Reporting](#41-citizen-pothole-reporting)
   - 4.2 [AI Pothole Detection Engine](#42-ai-pothole-detection-engine)
   - 4.3 [Road Quality Scoring](#43-road-quality-scoring)
   - 4.4 [Intelligent Route Recommendation](#44-intelligent-route-recommendation)
   - 4.5 [Municipality Maintenance Logging](#45-municipality-maintenance-logging)
   - 4.6 [Voice-Enabled Reporting (Multilingual)](#46-voice-enabled-reporting-multilingual)
5. [Data Models](#5-data-models)
6. [Deep Learning Model Design](#6-deep-learning-model-design)
7. [Road Quality Score Algorithm](#7-road-quality-score-algorithm)
8. [Geospatial Concentration Engine](#8-geospatial-concentration-engine)
9. [Technology Stack](#9-technology-stack)
10. [API Design](#10-api-design)
11. [Google Maps Integration Strategy](#11-google-maps-integration-strategy)
12. [Database Design](#12-database-design)
13. [Mobile App Design](#13-mobile-app-design)
14. [Municipality Dashboard](#14-municipality-dashboard)
15. [Privacy, Security & Data Governance](#15-privacy-security--data-governance)
16. [Phased Rollout Plan](#16-phased-rollout-plan)
17. [Risk Analysis](#17-risk-analysis)
18. [Open Questions & Future Enhancements](#18-open-questions--future-enhancements)

---

## 1. Problem Statement

Bengaluru's road infrastructure suffers from a persistent and severe pothole problem. Despite BBMP (Bruhat Bengaluru Mahanagara Palike) maintenance efforts, citizens face:

- **No real-time road quality information** when choosing routes.
- **Fragmented reporting** — most people use Twitter, 311-like helplines, or nothing at all.
- **Current map apps (Google Maps, Apple Maps) only factor distance + traffic** — a route that is faster in distance may be far more damaging to vehicles and dangerous to riders.
- **Lack of accountability** for municipalities — pothole repairs have no closed-loop system.
- **Language barriers** — significant portion of Bengaluru residents are more comfortable in Kannada or Hindi than English.

The result: Drivers unknowingly choose routes with heavy pothole concentration, leading to vehicle damage, accidents, and wasted commute time.

---

## 2. Product Vision & Goals

**Vision:** Build a community-powered, AI-assisted road intelligence platform that helps Bengaluru residents choose safer routes and holds the municipality accountable for road maintenance.

### Goals

| Goal | Success Metric |
|------|---------------|
| Enable citizen pothole reporting | ≥ 10,000 verified reports in Year 1 |
| Provide route quality scoring | Route quality layer live on Google Maps integration |
| Reduce vehicle damage & accidents on known bad roads | User-reported satisfaction surveys |
| Give BBMP a repair prioritisation tool | BBMP adoption or data feed integration |
| Support Kannada/Hindi/English voice reporting | Voice input adoption ≥ 30% of reports |

---

## 3. System Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    MOBILE APP (Flutter)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Report      │  │  Route       │  │  Voice Input  │  │
│  │  Pothole     │  │  Planner     │  │  (Bhashini)   │  │
│  │  (Photo+GPS) │  │  (Maps SDK)  │  │  Kan/Hin/Eng  │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘  │
└─────────┼────────────────┼──────────────────┼───────────┘
          │                │                  │
          ▼                ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│               API GATEWAY (FastAPI / Python)            │
│  /reports  /route-score  /maintenance  /voice-report    │
└─────────┬───────────────┬─────────────────┬─────────────┘
          │               │                 │
    ┌─────▼────┐   ┌──────▼──────┐   ┌──────▼──────┐
    │ Pothole  │   │  Route      │   │ Maintenance │
    │ ML Engine│   │  Scoring    │   │  Logger     │
    │(YOLOv8 + │   │  Engine     │   │  (BBMP API) │
    │ Mask R-  │   │  (PostGIS + │   │             │
    │  CNN)    │   │   H3)       │   │             │
    └─────┬────┘   └──────┬──────┘   └──────┬──────┘
          │               │                 │
          ▼               ▼                 ▼
┌─────────────────────────────────────────────────────────┐
│          PostGIS (Spatial DB)  +  Firebase (Realtime)   │
│  potholes, road_segments, maintenance_log, route_cache  │
└─────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│         BBMP Municipality Dashboard (React Web)         │
│    Heatmaps, Repair Queues, Route Quality Reports       │
└─────────────────────────────────────────────────────────┘
```

### Component Summary

| Component | Technology | Role |
|-----------|-----------|------|
| Mobile App | Flutter | Reporting, navigation, voice |
| API Gateway | FastAPI (Python) | Routes all requests |
| ML Engine | YOLOv8 + Mask R-CNN (PyTorch) | Detect potholes, estimate severity |
| Spatial DB | PostGIS (PostgreSQL) | Store, cluster, query all geo data |
| Realtime Sync | Firebase Firestore | Live report feeds |
| Spatial Index | H3 (Uber) | Hexagonal tile-based density scoring |
| Voice Input | Bhashini / Google Speech | Kannada / Hindi / English ASR |
| Maps | Google Maps SDK + Routes API | Route display and comparison |
| Dashboard | React + Deck.gl | BBMP visualisation portal |

---

## 4. Feature Breakdown

### 4.1 Citizen Pothole Reporting

**What it does:** Allows any citizen to submit a pothole report via photo, GPS location, and optional description.

**Flow:**
1. User opens app and taps "Report Pothole".
2. App requests camera permission and captures or uploads a photo.
3. GPS coordinates are auto-captured (with optional manual pin correction on map).
4. User can optionally add a voice/text description (Kannada/Hindi/English).
5. Report is uploaded to the API. The ML engine asynchronously validates and scores the image.
6. User receives a confirmation with a report ID and the reported location marked on the map.
7. If the same location receives ≥ 3 reports within 50m, it is auto-escalated to BBMP queue.

**Edge Cases:**
- No internet: reports stored locally (SQLite) and synced when back online.
- Duplicate submission: system deduplicates using H3 cell + 72-hour window.
- Invalid image (no road visible): ML engine flags for human review rather than rejecting outright.

---

### 4.2 AI Pothole Detection Engine

**What it does:** Processes submitted images to confirm pothole presence, estimate severity, and extract pothole pixel-area (concentration metric).

**Two-stage pipeline:**

| Stage | Model | Purpose |
|-------|-------|---------|
| Stage 1: Detection | YOLOv8n (on-device, optional) | Fast binary classification: pothole / no-pothole |
| Stage 2: Severity | Mask R-CNN (server-side) | Segment the pothole, estimate pixel area → severity class |

**Severity Classes:**

| Class | Pixel Area (% of frame) | Description |
|-------|------------------------|-------------|
| Low | < 2% | Minor surface crack / small pothole |
| Medium | 2–8% | Moderate pothole, slow-down advised |
| High | 8–20% | Large pothole, vehicle damage risk |
| Critical | > 20% | Road hazard, impassable for two-wheelers |

**Training Data:**
- Kaggle Pothole Detection Dataset
- Custom Bengaluru street photos (crowdsourced via the app itself)
- Data augmentation: brightness, rain/wet surface simulation, motion blur

**Model Serving:**
- YOLOv8 exported to TFLite for optional on-device pre-screening.
- Mask R-CNN runs on FastAPI backend (NVIDIA T4 GPU recommended).

---

### 4.3 Road Quality Scoring

**What it does:** Assigns a quality score (0–100, higher = better) to every road segment, inspired by the **Pavement Condition Index (PCI)** standard.

**Key principle — Concentration over Count:**
> A 1 km stretch with 20 potholes clustered tightly in 100m is far worse than a 6 km road with 20 potholes spread evenly. The score must penalise concentration, not just total count.

**Score components:**

```
Segment Score = 100 − (Severity_Penalty + Concentration_Penalty + Recency_Penalty)
```

- **Severity Penalty:** Weighted sum of individual pothole severities on segment.
- **Concentration Penalty:** Derived from Kernel Density Estimate (KDE) peak value on the segment. High local density → large penalty.
- **Recency Penalty:** Older reports are decayed with a half-life of 30 days (maintenance may have occurred).

See [Section 7](#7-road-quality-score-algorithm) for the full algorithm.

---

### 4.4 Intelligent Route Recommendation

**What it does:** Presents users with Google Maps route alternatives, each augmented with a Road Quality Score, so they can trade off speed, traffic, and road condition.

**Flow:**
1. User enters source and destination.
2. App calls Google Maps Routes API requesting up to 3 route alternatives.
3. Backend intersects each route polyline with the PostGIS pothole database.
4. Each route is scored using the Road Quality algorithm.
5. App displays all routes colour-coded:
   - 🟢 Green: Quality score ≥ 75
   - 🟡 Yellow: Quality score 50–74
   - 🔴 Red: Quality score < 50
6. User sees a summary card per route:
   - Distance | ETA | Road Quality Score | Pothole Hotspots count
7. User chooses their preferred route.

**Route weighting (custom):**
- Google Maps does not expose per-segment cost injection natively.
- Workaround: fetch multiple alternatives, post-score them server-side, re-rank and annotate.
- Advanced option: use **Valhalla open-source routing engine** for true custom cost routing (Phase 2).

---

### 4.5 Municipality Maintenance Logging

**What it does:** Allows BBMP/municipality officials to log completed road maintenance, which triggers automatic score refresh for affected segments.

**Flow:**
1. BBMP official logs into the Municipality Dashboard.
2. They mark a road segment (polyline or address range) as "Under Maintenance" or "Repaired".
3. System creates a `maintenance_log` entry with timestamp, segment ID, work type.
4. All pothole records within that segment are marked `status = archived`.
5. Road Quality Score for that segment is recalculated (boosted).
6. If maintenance is "Utility Work" (water/cable/gas pipeline), segment is flagged as "Potential new potholes expected" — score gets a pre-emptive mild penalty for 90 days.
7. Citizens see the segment marked with a construction icon on the app map.

**Why utility work matters:**
> A common Bengaluru pattern: BBMP digs roads for water/electricity work, patches poorly, and new potholes form within weeks. Logging this work pre-emptively flags the segment and expects re-reports.

---

### 4.6 Voice-Enabled Reporting (Multilingual)

**What it does:** Lets users submit a pothole report entirely by voice in Kannada, Hindi, or English.

**Languages supported:**

| Language | Code | ASR Provider |
|----------|------|-------------|
| Kannada | `kn-IN` | Bhashini (primary), Google Speech-to-Text (fallback) |
| Hindi | `hi-IN` | Bhashini (primary), Google Speech-to-Text (fallback) |
| English | `en-IN` | Google Speech-to-Text |

**Voice command examples (structured commands perform best):**

| Kannada | Hindi | English |
|---------|-------|---------|
| "ಗುಂಡಿ ವರದಿ ಮಾಡಿ" (Report pothole) | "गड्ढा रिपोर्ट करें" | "Report a pothole here" |
| "ದೊಡ್ಡ ಗುಂಡಿ, ಹೆಚ್ಚು ಅಪಾಯ" (Big pothole, high danger) | "बड़ा गड्ढा, खतरनाक है" | "Big pothole, dangerous" |

**Technical Implementation:**
- Flutter `speech_to_text` plugin (wraps platform ASR).
- For Bhashini: HTTP call to `api.bhashini.gov.in/asr` with audio blob.
- NLP intent extraction: lightweight rule-based parser maps voice transcript to structured report fields (severity, additional notes).
- Fallback: if ASR confidence < 0.7, prompt user to re-speak or switch to text.

---

## 5. Data Models

### `pothole_report`
```sql
id              UUID PRIMARY KEY
location        GEOGRAPHY(POINT, 4326)   -- WGS84 lat/lng
h3_index_r9     VARCHAR(15)              -- H3 resolution-9 cell
image_url       TEXT
severity        ENUM('low','medium','high','critical')
ml_confidence   FLOAT                    -- 0.0–1.0
pixel_area_pct  FLOAT                    -- % of image frame
status          ENUM('pending','verified','archived','disputed')
reported_by     UUID (FK users)
reported_at     TIMESTAMPTZ
road_segment_id UUID (FK road_segments)  -- snapped via Roads API
source          ENUM('photo','voice','passive_sensor')
description     TEXT
```

### `road_segment`
```sql
id              UUID PRIMARY KEY
osm_way_id      BIGINT                   -- OpenStreetMap way ID
name            TEXT                     -- Road name
geometry        GEOGRAPHY(LINESTRING, 4326)
quality_score   FLOAT                    -- 0–100 (PCI-inspired)
score_updated_at TIMESTAMPTZ
pothole_count   INT                      -- active verified potholes
concentration_peak FLOAT                -- KDE peak density value
under_maintenance BOOLEAN DEFAULT FALSE
```

### `maintenance_log`
```sql
id              UUID PRIMARY KEY
road_segment_id UUID (FK road_segments)
work_type       ENUM('repair','utility_dig','resurfacing','patching')
status          ENUM('planned','in_progress','completed')
logged_by       UUID (FK bbmp_users)
started_at      TIMESTAMPTZ
completed_at    TIMESTAMPTZ
notes           TEXT
affected_bbox   GEOGRAPHY(POLYGON, 4326)
```

### `user`
```sql
id              UUID PRIMARY KEY
phone           VARCHAR(15) UNIQUE       -- primary auth (OTP)
preferred_lang  ENUM('kn','hi','en') DEFAULT 'en'
created_at      TIMESTAMPTZ
total_reports   INT DEFAULT 0
reputation_score FLOAT DEFAULT 1.0      -- for report credibility weighting
```

---

## 6. Deep Learning Model Design

### Pipeline

```
Input Image (User Photo)
        │
        ▼
  ┌─────────────┐
  │  YOLOv8n    │ ──── No pothole detected ──→ Flag for human review
  │  (on-device │
  │   optional) │
  └─────┬───────┘
        │ Pothole detected (confidence > 0.5)
        ▼
  ┌─────────────┐
  │  Mask R-CNN │  Server-side
  │  Segmentation│──→ Pixel mask → area_pct → severity_class
  └─────┬───────┘
        │
        ▼
  Structured Output:
  { detected: true, severity: "high",
    pixel_area_pct: 12.4, confidence: 0.87 }
```

### Model Training Details

**YOLOv8 (Detection)**
- Base: `yolov8n.pt` (nano, 3.2M params)
- Fine-tune on: Roboflow Pothole dataset + Bengaluru custom data
- Input: 640×640 RGB
- Output: bounding boxes + confidence
- Target mAP@0.5: ≥ 85%
- Export: TFLite INT8 for mobile (~14MB)

**Mask R-CNN (Severity)**
- Base: ResNet-50 backbone, pretrained on COCO
- Fine-tune: annotated with severity labels (Low/Medium/High/Critical)
- Input: full resolution image (server-side, no size constraint)
- Output: instance segmentation masks + severity classification
- Serve via: TorchServe on FastAPI backend

### Training Pipeline
```
Raw Reports (images) → Manual Annotation (Label Studio)
                             ↓
                   Augmentation Pipeline (Albumentations)
                   - Rain simulation
                   - Glare / wet road
                   - Motion blur
                   - Night conditions
                             ↓
                   YOLOv8 Fine-tune → Export TFLite
                   Mask R-CNN Fine-tune → TorchServe
                             ↓
                   MLflow for experiment tracking
                   Monthly re-train as new reports accumulate
```

---

## 7. Road Quality Score Algorithm

### Formula

The score for a road segment `S` of length `L` is computed as:

```
Score(S) = 100 - min(100, Severity_Penalty(S) + Concentration_Penalty(S) + Recency_Penalty(S))
```

Where:

**Severity Penalty:**
```
severity_weights = { low: 1, medium: 3, high: 7, critical: 15 }

Severity_Penalty(S) = Σ (weight[pᵢ.severity] × pᵢ.ml_confidence) / L_km × k₁
```
- `L_km` = segment length in km (normalises for segment length)
- `k₁` = tuning constant (default: 5)

**Concentration Penalty (the critical innovation):**
```
For each 100m sub-window w within S:
  density(w) = count of potholes in w

Concentration_Penalty(S) = max_density_window / (L_km × 10) × k₂
```
- This is effectively the **peak pothole density in any 100m sub-window**.
- A 6km road with 20 potholes all in 1 window scores far worse than 20 spread evenly.
- `k₂` = tuning constant (default: 10)

**Recency Penalty (decay):**
```
age_days = current_date - report.reported_at
decay_factor = exp(-age_days / 30)   # half-life of 30 days

Recency_Penalty(S) = Σ decay_factor(pᵢ) × severity_weight(pᵢ) / L_km × k₃
```
- Newer reports have more weight; old unconfirmed reports fade out.
- After 90 days without re-report, weight approaches ~5% of original.
- `k₃` = tuning constant (default: 2)

### Score Interpretation

| Score | Label | Map Color | Recommendation |
|-------|-------|-----------|---------------|
| 75–100 | Good | 🟢 Green | Standard route |
| 50–74 | Fair | 🟡 Yellow | Proceed with caution |
| 25–49 | Poor | 🟠 Orange | Avoid if alternative exists |
| 0–24 | Critical | 🔴 Red | Strong avoid; risk of damage |

### Score Refresh Triggers
- New pothole report verified on segment → immediate rescore
- Maintenance log: `completed` → full rescore (all potholes archived)
- Maintenance log: `utility_dig` → apply -10 pre-emptive penalty for 90 days
- Scheduled daily re-score for decay updates

---

## 8. Geospatial Concentration Engine

### H3 Hexagonal Indexing

All pothole points are indexed using **Uber H3 at resolution 9** (~174m edge-length hexagons, ~105m² area). This provides:
- O(1) lookup: given a GPS point, instantly find its H3 cell.
- Aggregation: sum/weight potholes within a cell for density scoring.
- Hierarchical zoom: resolution 7 (city level) → 9 (street level) → 11 (very fine).

```python
import h3

def get_h3_index(lat, lng, resolution=9):
    return h3.latlng_to_cell(lat, lng, resolution)

def get_neighboring_cells(h3_index, k_rings=1):
    return h3.grid_disk(h3_index, k_rings)
```

### Concentration Query (PostGIS)

For a given route polyline, find all potholes within 50m of the route:

```sql
SELECT
    p.id,
    p.severity,
    p.location,
    p.reported_at,
    ST_Distance(p.location, route.geom) AS dist_from_route,
    -- Project onto route to get linear position (0–1)
    ST_LineLocatePoint(route.geom, p.location::geometry) AS route_fraction
FROM pothole_report p,
     (SELECT ST_GeomFromText(:route_wkt, 4326) AS geom) route
WHERE ST_DWithin(p.location::geography, route.geom::geography, 50)  -- 50m buffer
  AND p.status = 'verified'
ORDER BY route_fraction;
```

The `route_fraction` (0.0 to 1.0) tells us **where on the route** the pothole is — enabling sliding window concentration analysis.

### DBSCAN for Hotspot Detection (Offline/Dashboard)

```python
from sklearn.cluster import DBSCAN
import numpy as np

def find_pothole_hotspots(pothole_coords, eps_meters=100, min_samples=5):
    """
    eps_meters: cluster radius in meters (~0.001 deg at Bengaluru latitude)
    min_samples: minimum potholes to form a hotspot
    """
    coords_rad = np.radians(pothole_coords)
    db = DBSCAN(eps=eps_meters/111320, min_samples=min_samples, metric='haversine')
    labels = db.fit_predict(coords_rad)
    return labels  # -1 = noise, >=0 = cluster ID
```

---

## 9. Technology Stack

### Full Stack Summary

| Layer | Technology | Justification |
|-------|-----------|--------------|
| **Mobile** | Flutter 3.x | Best TFLite integration; Google Maps SDK native; single codebase for Android + iOS |
| **ML Backend** | FastAPI + PyTorch | Co-located with Mask R-CNN; async endpoints; easy GPU access |
| **On-device ML** | TFLite (YOLOv8 INT8) | Pre-screening on device reduces unnecessary server calls |
| **Spatial Database** | PostgreSQL + PostGIS | Full spatial analytics; `ST_ClusterDBSCAN`; road network queries |
| **Real-time Sync** | Firebase Firestore | Live pothole feed without polling; offline persistence |
| **Spatial Index** | H3 (Uber) | Fast density queries; hierarchical aggregation |
| **Voice/ASR** | Bhashini API + Google Speech | Bhashini for Kannada (free, India-trained); Google as fallback |
| **Maps** | Google Maps SDK + Routes API | Route alternatives + polyline rendering |
| **Routing (Phase 2)** | Valhalla (open-source) | Custom cost routing; self-hosted |
| **Dashboard** | React + Deck.gl + Kepler.gl | Rich geospatial visualisations for BBMP |
| **Auth** | Firebase Auth (OTP) | Phone OTP login — no email required |
| **ML Tracking** | MLflow | Experiment tracking; model versioning |
| **Infrastructure** | GCP (Cloud Run + Cloud SQL) | Managed, scales to zero; PostGIS on Cloud SQL |
| **CDN / Storage** | GCS (Google Cloud Storage) | Image storage for reports |

### Dependency Map
```
Flutter App
  ├── google_maps_flutter
  ├── geolocator
  ├── speech_to_text (Bhashini/Google)
  ├── camera
  ├── tflite_flutter (YOLOv8 on-device)
  ├── firebase_core + firebase_firestore
  └── dio (HTTP client)

FastAPI Backend
  ├── torch + torchvision (Mask R-CNN)
  ├── ultralytics (YOLOv8)
  ├── h3 (Uber H3 indexing)
  ├── geopandas + shapely
  ├── psycopg2 + sqlalchemy (PostGIS)
  ├── boto3/gcs-client (image storage)
  └── mlflow (model registry)
```

---

## 10. API Design

### Base URL: `https://api.pothole-blr.in/v1`

### Endpoints

#### `POST /reports`
Submit a new pothole report.

**Request:**
```json
{
  "lat": 12.9716,
  "lng": 77.5946,
  "image_base64": "...",
  "severity_hint": "high",
  "description": "ದೊಡ್ಡ ಗುಂಡಿ",
  "source": "photo"
}
```
**Response:**
```json
{
  "report_id": "uuid",
  "status": "pending_verification",
  "h3_cell": "8a3969a3a2fffff",
  "road_segment_id": "uuid",
  "estimated_verification_time_seconds": 30
}
```

---

#### `GET /route/score`
Get quality scores for multiple route alternatives.

**Request:**
```
GET /route/score?origin=12.9716,77.5946&destination=12.9352,77.6245&alternatives=3
```
**Response:**
```json
{
  "routes": [
    {
      "route_id": "r1",
      "polyline": "encoded_polyline_string",
      "distance_km": 8.2,
      "eta_minutes": 22,
      "quality_score": 72,
      "quality_label": "Fair",
      "hotspot_count": 3,
      "worst_segment": {
        "name": "Outer Ring Road near Marathahalli",
        "score": 31,
        "lat": 12.955,
        "lng": 77.698
      }
    }
  ]
}
```

---

#### `POST /maintenance`
Log a maintenance event (BBMP-auth required).

**Request:**
```json
{
  "road_segment_id": "uuid",
  "work_type": "utility_dig",
  "status": "in_progress",
  "affected_bbox": [[12.97, 77.59], [12.98, 77.61]],
  "notes": "BESCOM cable laying work"
}
```

---

#### `GET /heatmap`
Return H3 hexagon density data for map rendering.

```
GET /heatmap?bbox=12.85,77.48,13.10,77.75&resolution=9
```
**Response:** GeoJSON FeatureCollection of H3 hexagons with `quality_score` properties.

---

## 11. Google Maps Integration Strategy

### Why Google Maps can't natively score routes by pothole density

The Google Maps Routes API returns up to 3 alternative routes and polylines, but does **not** allow injecting custom per-segment costs or weights into its routing engine. The routing is purely distance + traffic + road type.

### Our Workaround (Phase 1)

```
1. Call Routes API → get up to 3 alternatives (polylines)
2. Decode each polyline to a set of lat/lng points
3. For each route: query PostGIS for all potholes within 50m of the polyline
4. Compute Road Quality Score per route using our algorithm
5. Display all 3 routes in the Maps SDK with colour-coding
6. Show quality score overlaid on each route card
```

This gives users the quality context they need, even though routing itself is still handled by Google.

### Phase 2: Valhalla Custom Routing

For true quality-weighted routing (find the optimal route that balances distance + road quality):
- Deploy Valhalla open-source routing engine with Bengaluru OSM data.
- Modify the **edge cost function** to include our quality scores as additional weight.
- Expose as `/route/optimised?mode=quality_balanced` endpoint.
- Still use Google Maps SDK for display; only the routing computation changes.

### Map Layer Overlays

| Layer | Purpose |
|-------|---------|
| H3 Heatmap | Overall road quality at city/neighbourhood zoom |
| Pothole Markers | Individual verified reports (zoom level ≥ 15) |
| Maintenance Overlay | Yellow diagonal stripes on under-maintenance segments |
| Route Quality Colour | Green/Yellow/Orange/Red per route alternative |

---

## 12. Database Design

### Schema (PostGIS + PostgreSQL)

```sql
-- Enable extensions
CREATE EXTENSION postgis;
CREATE EXTENSION h3;

-- Core tables (abbreviated)

CREATE TABLE road_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    osm_way_id BIGINT UNIQUE,
    name TEXT,
    geometry GEOGRAPHY(LINESTRING, 4326),
    quality_score FLOAT DEFAULT 100.0,
    score_updated_at TIMESTAMPTZ DEFAULT now(),
    under_maintenance BOOLEAN DEFAULT FALSE
);

CREATE TABLE pothole_report (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location GEOGRAPHY(POINT, 4326) NOT NULL,
    h3_index_r9 VARCHAR(15),
    road_segment_id UUID REFERENCES road_segments(id),
    severity VARCHAR(10),
    ml_confidence FLOAT,
    pixel_area_pct FLOAT,
    status VARCHAR(20) DEFAULT 'pending',
    reported_at TIMESTAMPTZ DEFAULT now()
);

-- Spatial indexes for performance
CREATE INDEX idx_pothole_location ON pothole_report USING GIST(location);
CREATE INDEX idx_segment_geometry ON road_segments USING GIST(geometry);
CREATE INDEX idx_pothole_h3 ON pothole_report(h3_index_r9);
CREATE INDEX idx_pothole_status ON pothole_report(status);
```

### Query: Route intersection (used by scoring engine)
```sql
-- Find all verified potholes within 50m of a route, with their linear position
WITH route AS (
    SELECT ST_GeographyFromText('LINESTRING(77.59 12.97, 77.62 12.95, ...)') AS geom
)
SELECT
    p.id, p.severity, p.ml_confidence, p.reported_at,
    ST_LineLocatePoint(
        route.geom::geometry,
        p.location::geometry
    ) AS route_fraction
FROM pothole_report p, route
WHERE ST_DWithin(p.location, route.geom, 50)
  AND p.status = 'verified'
ORDER BY route_fraction;
```

---

## 13. Mobile App Design

### Screens

```
├── Splash / Onboarding (language selection: ಕನ್ನಡ / हिंदी / English)
├── Home
│   ├── Map View (Google Maps + quality heatmap)
│   ├── "Report Pothole" FAB button
│   └── "Plan Route" search bar
├── Report Pothole Screen
│   ├── Camera capture
│   ├── GPS auto-location (with manual pin)
│   ├── Severity hint (optional)
│   ├── Voice input button (mic icon)
│   └── Submit
├── Route Planner Screen
│   ├── Source / Destination input
│   ├── Route alternatives (3 cards, quality-colour coded)
│   ├── Route detail: map + quality markers
│   └── "Navigate" → hands off to Google Maps
├── My Reports (history of user's submissions)
├── Nearby Potholes (list view, sorted by distance)
└── Settings (language, notifications)
```

### UX Principles

- **Minimal friction for reporting:** ≤ 3 taps from home screen to submit a report.
- **Offline-first:** Pending reports survive app restarts and no-connectivity situations.
- **Accessible:** Support for large text, high contrast mode.
- **Language-aware:** All UI strings externalised; full Kannada, Hindi, English localisation.

---

## 14. Municipality Dashboard

A separate web portal (React) for BBMP officials and admins.

### Features

| Feature | Description |
|---------|-------------|
| City Heatmap | Deck.gl H3 heatmap of quality scores, filterable by ward |
| Pothole List | Sortable/filterable table of all reports with status management |
| Repair Queue | Auto-generated priority queue (sorted by severity × concentration × age) |
| Maintenance Logger | Log repair/utility work; triggers score refresh |
| Ward Report | Per-ward summary of road quality trends over time |
| Analytics | Weekly/monthly report count trends, improvement tracking |
| Export | CSV/PDF export of reports for official records |

### Repair Priority Score

```
Priority = severity_weight × concentration_score × (days_since_first_report / 30) × report_count
```

Higher priority → top of BBMP repair queue.

---

## 15. Privacy, Security & Data Governance

| Concern | Approach |
|---------|---------|
| User Identity | Phone OTP login only; no PII required beyond phone number |
| Photo Privacy | Images stored in private GCS bucket; only shared with BBMP, never public-facing in full resolution |
| GPS Accuracy | Location snapped to road (±50m precision displayed); raw GPS not exposed publicly |
| Report Abuse | Rate limiting: max 10 reports/user/hour; ML confidence gate (< 0.4 → human review) |
| BBMP Data Access | Role-based auth; BBMP officials only see aggregate scores + anonymised report locations |
| Data Retention | Raw images retained 6 months; archived after pothole resolved; user can delete own reports |
| PDPB Compliance | Aligns with India's Personal Data Protection Bill principles; no data sold or shared commercially |

---

## 16. Phased Rollout Plan

### Phase 1 — MVP (Months 1–4)

**Goal:** Prove the core loop works.

- [ ] Flutter app: photo reporting + GPS + map view
- [ ] FastAPI backend: report ingestion + YOLOv8 detection
- [ ] PostGIS DB: pothole storage + basic road segment scoring
- [ ] Google Maps: display pothole markers on map
- [ ] Basic route scoring (Google Routes API + our PostGIS intersection)
- [ ] BBMP Dashboard v1: heatmap + report list
- [ ] Launch in 2 wards (Koramangala, Whitefield) for pilot

**Success criteria:** 500 verified reports in 4 weeks; quality scores computed for ≥ 100 road segments.

---

### Phase 2 — Quality & Voice (Months 5–8)

**Goal:** Improve accuracy and add multilingual voice.

- [ ] Mask R-CNN severity scoring (upgrade from binary detection)
- [ ] Concentration algorithm: sliding window density + KDE
- [ ] Bhashini voice integration (Kannada + Hindi)
- [ ] Maintenance logging module (BBMP portal)
- [ ] Score refresh on maintenance events
- [ ] Expand to all BBMP wards
- [ ] Notification: user notified when their reported pothole is fixed

---

### Phase 3 — Custom Routing (Months 9–12)

**Goal:** True quality-weighted route optimisation.

- [ ] Valhalla deployment with Bengaluru OSM data
- [ ] Custom edge cost function integrating quality scores
- [ ] Passive sensing mode (accelerometer + GPS background track)
- [ ] BBMP API integration for official data exchange
- [ ] App Store / Play Store public launch
- [ ] Performance benchmark and model retraining cycle

---

### Phase 4 — Scale & Partnerships (Year 2)

- [ ] Expand to other Karnataka cities (Mysuru, Mangaluru)
- [ ] Insurance company partnerships (vehicle damage routing data)
- [ ] Integration with BBMP 311 helpline
- [ ] Open data API for researchers and journalists
- [ ] Predictive maintenance: ML model predicting pothole formation post-monsoon

---

## 17. Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Low citizen adoption | Medium | High | Simple UX; Kannada-first; onboard auto-rickshaw/delivery driver community |
| BBMP non-cooperation | High | Medium | Design for standalone value even without BBMP; use data as leverage |
| Poor Kannada ASR accuracy | Medium | Medium | Structured voice commands; text fallback always available |
| ML model false positives | Medium | Medium | Confidence threshold gate; human review queue |
| Google Maps API cost | Low | Medium | Cache route scores aggressively; use Maps SDK free tier for display |
| Data staleness (repairs not logged) | High | High | Automatic decay weighting; encourage re-reports; BBMP data feeds |
| Monsoon data quality (wet roads) | Medium | Medium | Training data augmentation with wet/rain conditions |
| Privacy concerns | Low | High | Clear privacy policy; minimal data collection; no photos made public |

---

## 18. Open Questions & Future Enhancements

### Open Questions for Product Decisions
1. **Gamification:** Should users earn points/badges for reporting? Risk: gaming the system with fake reports.
2. **BBMP Integration Depth:** Will BBMP provide official API access, or do we operate independently and share data unilaterally?
3. **Report Credibility:** How to weight reports from new users vs. established users? (Reputation system vs. flat weighting.)
4. **Real-time vs. Batch scoring:** Route score should be near-real-time for the app; how frequently do we recompute segment scores?

### Future Enhancements
- **Video reporting:** Extract frames from short video to auto-detect and count multiple potholes per submission.
- **Dashcam integration:** Auto-detect potholes from parked/moving vehicle dashcam feeds.
- **Predictive model:** Forecast pothole formation probability post-monsoon based on road age, drainage quality, traffic volume.
- **IoT sensors:** Municipal vehicles equipped with accelerometers to passively sweep road quality.
- **WhatsApp bot reporting:** Allow reporting via WhatsApp Business API — much higher adoption potential in India.
- **Pothole depth estimation:** Using stereo photogrammetry or phone LiDAR (iPhone 12+) to estimate 3D depth.

---

## Appendix: Key References & Datasets

| Resource | URL / Source |
|---------|-------------|
| Roboflow Pothole Dataset | roboflow.com/pothole-detection |
| BBMP GIS Portal | bbmpmaps.bbmp.gov.in |
| OpenStreetMap Bengaluru | openstreetmap.org (Bengaluru extract) |
| Bhashini ASR API | bhashini.gov.in / api.bhashini.gov.in |
| H3 Hexagonal Grid | h3geo.org |
| Valhalla Routing Engine | github.com/valhalla/valhalla |
| Google Maps Routes API | developers.google.com/maps/documentation/routes |
| PCI (Pavement Condition Index) | ASTM D6433 Standard |
| ULCA (MeitY) | ulca.in |

---

*Document maintained by the Bengaluru Pothole Assistant project team.*  
*For questions, open an issue in the project repository.*
