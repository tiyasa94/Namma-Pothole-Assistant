"""
Seed script — populate the DB with realistic mock pothole reports.

Images source: Synthetically generated road/pothole images in assets/images/
(run scripts/generate_images.py first, or pass --generate to auto-run it).

GPS coordinates: real Bengaluru road junctions (BBMP complaint data, 2023).

Usage:
  python scripts/seed_data.py                   # seed using existing images
  python scripts/seed_data.py --generate        # regenerate images then seed
  python scripts/seed_data.py --clear           # wipe existing records first
  python scripts/seed_data.py --generate --clear
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from api.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "images"

# ── Seed report definitions ────────────────────────────────────────────────────
# Each entry maps 1:1 to a generated image in assets/images/
SEED_REPORTS = [
    # (image_file, lat, lng, road_name, severity)
    ("pothole_001.jpg", 12.9558, 77.6980, "Outer Ring Road, Marathahalli",       "critical"),
    ("pothole_002.jpg", 12.9352, 77.6245, "Sarjapur Road, Bellandur",            "high"),
    ("pothole_003.jpg", 13.0358, 77.5970, "Hennur Main Road, Banaswadi",         "high"),
    ("pothole_004.jpg", 12.9716, 77.5946, "MG Road underpass, Central",          "medium"),
    ("pothole_005.jpg", 12.9784, 77.6408, "Indiranagar 100ft Road",              "medium"),
    ("pothole_006.jpg", 12.9698, 77.7499, "Whitefield Main Road, ITPL junction", "critical"),
    ("pothole_007.jpg", 13.0160, 77.5550, "Tumkur Road, Goraguntepalya",         "high"),
    ("pothole_008.jpg", 12.9121, 77.6446, "Hosur Road, Electronic City Phase 2", "critical"),
    ("pothole_009.jpg", 13.0630, 77.5930, "Bellary Road, near Hebbal flyover",   "medium"),
    ("pothole_010.jpg", 12.8999, 77.5950, "Bannerghatta Road, J.P. Nagar 7th",   "high"),
    ("pothole_011.jpg", 12.9279, 77.5748, "Kanakapura Road, Jayanagar",          "medium"),
    ("pothole_012.jpg", 13.0000, 77.6840, "Old Madras Road, KR Puram",           "high"),
    ("pothole_013.jpg", 12.9825, 77.5533, "Chord Road, Rajajinagar",             "medium"),
    ("pothole_014.jpg", 12.9199, 77.6230, "Koramangala 5th Block inner road",    "low"),
    ("pothole_015.jpg", 12.9450, 77.6140, "BTM Layout 2nd Stage",                "medium"),
    ("pothole_016.jpg", 13.0730, 77.6310, "Thanisandra Main Road",               "critical"),
    ("pothole_017.jpg", 12.8900, 77.6500, "Electronic City Expressway slip road","high"),
    ("pothole_018.jpg", 12.9650, 77.7100, "Kadugodi Main Road",                  "medium"),
    ("pothole_019.jpg", 13.0290, 77.6490, "Ramamurthy Nagar Main Road",          "high"),
    ("pothole_020.jpg", 12.9510, 77.5810, "Mysore Road, near Nayandahalli",      "low"),
]

SOURCES = ["photo", "photo", "photo", "voice"]

BASE_CONF = {"low": 0.52, "medium": 0.68, "high": 0.81, "critical": 0.91}
PIXEL_AREA = {"low": (0.5, 2.0), "medium": (2.0, 6.0), "high": (6.0, 15.0), "critical": (15.0, 28.0)}


def _random_reported_at(max_days_ago: int = 180) -> datetime:
    offset = random.randint(0, max_days_ago)
    return datetime.now(tz=timezone.utc) - timedelta(days=offset)


def _image_to_base64(path: Path) -> str:
    """Read a local image and return it as a base64 string."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _save_image_to_uploads(image_path: Path, uploads_dir: Path) -> str:
    """Copy an image to the uploads directory and return its URL path."""
    import hashlib, shutil
    with open(image_path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha1(raw).hexdigest()
    filename = f"{sha}.jpg"
    dest = uploads_dir / filename
    if not dest.exists():
        shutil.copy2(image_path, dest)
    return f"/uploads/{filename}"


async def seed(generate: bool = False, clear: bool = False):
    # Auto-generate images if requested or if assets are missing
    missing = [r for r in SEED_REPORTS if not (ASSETS_DIR / r[0]).exists()]
    if generate or missing:
        logger.info("Generating synthetic pothole images …")
        from scripts.generate_images import main as gen_main
        gen_main()

    # Resolve uploads dir (relative to project root)
    uploads_dir = Path(__file__).resolve().parent.parent / settings.LOCAL_STORAGE_PATH
    uploads_dir.mkdir(parents=True, exist_ok=True)

    dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    logger.info("Connected to database")

    try:
        if clear:
            await conn.execute("DELETE FROM pothole_report")
            logger.info("Cleared existing pothole_report rows")

        seg_row = await conn.fetchrow(
            "SELECT id FROM road_segments WHERE osm_way_id = 12345678 LIMIT 1"
        )
        orr_segment_id = str(seg_row["id"]) if seg_row else None
        logger.info("ORR segment id: %s", orr_segment_id)

        inserted = 0
        for i, (img_file, lat, lng, road, severity) in enumerate(SEED_REPORTS):
            img_path = ASSETS_DIR / img_file

            # Copy image to uploads/ and get the URL path
            if img_path.exists():
                image_url = _save_image_to_uploads(img_path, uploads_dir)
            else:
                logger.warning("  Image not found: %s — skipping image_url", img_path)
                image_url = None

            # Attach to ORR segment if near Marathahalli
            use_seg = (
                orr_segment_id
                if abs(lat - 12.9558) < 0.02 and abs(lng - 77.6980) < 0.02
                else None
            )

            ml_confidence = round(BASE_CONF[severity] + random.uniform(-0.05, 0.05), 3)
            lo, hi = PIXEL_AREA[severity]
            pixel_area = round(random.uniform(lo, hi), 2)
            reported_at = _random_reported_at()

            try:
                import h3 as h3lib
                h3_index = (
                    h3lib.latlng_to_cell(lat, lng, 9)
                    if hasattr(h3lib, "latlng_to_cell")
                    else h3lib.geo_to_h3(lat, lng, 9)
                )
            except Exception:
                h3_index = None

            await conn.execute(
                """
                INSERT INTO pothole_report
                    (id, location, h3_index_r9, image_url, severity,
                     ml_confidence, pixel_area_pct, status,
                     road_segment_id, source, description, reported_at)
                VALUES
                    ($1,
                     ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography,
                     $4, $5, $6, $7, $8, 'verified',
                     $9, $10, $11, $12)
                ON CONFLICT DO NOTHING
                """,
                str(uuid.uuid4()), lng, lat,
                h3_index, image_url, severity,
                ml_confidence, pixel_area, use_seg,
                random.choice(SOURCES),
                f"Pothole on {road}",
                reported_at,
            )
            inserted += 1
            img_status = "✓ image" if image_url else "✗ no image"
            logger.info("  [%2d] %-45s  %-8s  conf=%.2f  %s",
                        i + 1, road, severity, ml_confidence, img_status)

        logger.info("✅ Seeded %d pothole reports", inserted)

    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed mock pothole data")
    parser.add_argument("--generate", action="store_true",
                        help="(Re)generate synthetic images before seeding")
    parser.add_argument("--clear", action="store_true",
                        help="Delete all existing pothole_report rows first")
    args = parser.parse_args()
    asyncio.run(seed(generate=args.generate, clear=args.clear))
