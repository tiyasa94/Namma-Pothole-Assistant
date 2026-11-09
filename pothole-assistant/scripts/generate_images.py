"""
Generate synthetic pothole images for the prototype dataset.

Since external image downloads may be blocked in some environments,
this script creates realistic-looking road/pothole images programmatically
using PIL. The images are visually representative for UI/demo purposes.

Each image simulates:
  - Asphalt road surface (grey, textured)
  - A pothole (dark irregular depression)
  - Varying severity (size, depth appearance)
  - Realistic lighting conditions

Run: python scripts/generate_images.py
Output: assets/images/pothole_001.jpg ... pothole_020.jpg
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import numpy as np

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

IMG_SIZE = (640, 480)

# Severity configs: (min_radius, max_radius, min_count, max_count, darkness)
SEVERITY_CONFIGS = {
    "low":      (15, 35,  1, 2,  80),
    "medium":   (30, 60,  1, 3,  65),
    "high":     (50, 90,  2, 4,  50),
    "critical": (70, 130, 3, 5,  35),
}

SEED_REPORTS = [
    # (filename, severity, road_name)
    ("pothole_001.jpg", "critical", "Outer Ring Road, Marathahalli"),
    ("pothole_002.jpg", "high",     "Sarjapur Road, Bellandur"),
    ("pothole_003.jpg", "high",     "Hennur Main Road, Banaswadi"),
    ("pothole_004.jpg", "medium",   "MG Road underpass, Central"),
    ("pothole_005.jpg", "medium",   "Indiranagar 100ft Road"),
    ("pothole_006.jpg", "critical", "Whitefield Main Road, ITPL"),
    ("pothole_007.jpg", "high",     "Tumkur Road, Goraguntepalya"),
    ("pothole_008.jpg", "critical", "Hosur Road, Electronic City"),
    ("pothole_009.jpg", "medium",   "Bellary Road, Hebbal"),
    ("pothole_010.jpg", "high",     "Bannerghatta Road, JP Nagar"),
    ("pothole_011.jpg", "medium",   "Kanakapura Road, Jayanagar"),
    ("pothole_012.jpg", "high",     "Old Madras Road, KR Puram"),
    ("pothole_013.jpg", "medium",   "Chord Road, Rajajinagar"),
    ("pothole_014.jpg", "low",      "Koramangala 5th Block"),
    ("pothole_015.jpg", "medium",   "BTM Layout 2nd Stage"),
    ("pothole_016.jpg", "critical", "Thanisandra Main Road"),
    ("pothole_017.jpg", "high",     "Electronic City Expressway"),
    ("pothole_018.jpg", "medium",   "Kadugodi Main Road"),
    ("pothole_019.jpg", "high",     "Ramamurthy Nagar Main Road"),
    ("pothole_020.jpg", "low",      "Mysore Road, Nayandahalli"),
]


def _asphalt_texture(size: tuple[int, int], seed: int) -> Image.Image:
    """Generate a realistic asphalt road texture."""
    rng = np.random.default_rng(seed)
    w, h = size

    # Base grey road surface
    base = rng.integers(95, 125, size=(h, w), dtype=np.uint8)

    # Add aggregate texture (fine noise)
    noise = rng.integers(0, 25, size=(h, w), dtype=np.int16)
    texture = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Road markings — faint white line on left third
    if rng.random() > 0.5:
        x_mark = w // 3
        texture[:, max(0, x_mark-3):x_mark+3] = np.clip(
            texture[:, max(0, x_mark-3):x_mark+3].astype(np.int16) + 60, 0, 255
        ).astype(np.uint8)

    img = Image.fromarray(texture, mode="L").convert("RGB")

    # Slight warm tint (Indian roads tend to have reddish laterite dust)
    r, g, b = img.split()
    r = r.point(lambda p: min(255, p + 12))
    b = b.point(lambda p: max(0, p - 8))
    img = Image.merge("RGB", (r, g, b))

    return img


def _draw_pothole(
    draw: ImageDraw.ImageDraw,
    cx: int, cy: int,
    rx: int, ry: int,
    darkness: int,
    rng: np.random.Generator,
):
    """Draw a single irregular pothole depression."""
    # Outer shadow ring (cracked edges)
    for ring in range(4, 0, -1):
        scale = 1.0 + ring * 0.08
        shadow_color = min(255, darkness + ring * 18)
        draw.ellipse(
            [cx - rx * scale, cy - ry * scale,
             cx + rx * scale, cy + ry * scale],
            fill=(shadow_color, shadow_color - 5, shadow_color - 8),
        )

    # Inner dark pit
    draw.ellipse(
        [cx - rx, cy - ry, cx + rx, cy + ry],
        fill=(darkness, darkness - 3, darkness - 5),
    )

    # Water reflection glint (simulates waterlogged pothole)
    if rng.random() > 0.4:
        glint_x = cx + rng.integers(-rx // 3, rx // 3)
        glint_y = cy + rng.integers(-ry // 3, ry // 3)
        glint_r = rng.integers(3, max(4, rx // 5))
        draw.ellipse(
            [glint_x - glint_r, glint_y - glint_r,
             glint_x + glint_r, glint_y + glint_r],
            fill=(180, 195, 210),
        )


def generate_pothole_image(
    severity: str,
    seed: int,
    road_name: str = "",
) -> Image.Image:
    """Generate one synthetic pothole image for the given severity."""
    rng = np.random.default_rng(seed)
    w, h = IMG_SIZE

    # 1. Road surface background
    img = _asphalt_texture((w, h), seed=seed)
    draw = ImageDraw.Draw(img)

    # 2. Draw potholes
    cfg = SEVERITY_CONFIGS[severity]
    min_r, max_r, min_n, max_n, darkness = cfg
    n_holes = int(rng.integers(min_n, max_n + 1))

    for _ in range(n_holes):
        cx = int(rng.integers(w // 5, 4 * w // 5))
        cy = int(rng.integers(h // 4, 3 * h // 4))
        rx = int(rng.integers(min_r, max_r + 1))
        ry = int(rng.integers(int(rx * 0.6), int(rx * 1.0) + 1))
        _draw_pothole(draw, cx, cy, rx, ry, darkness, rng)

    # 3. Apply slight blur to soften harsh edges (more photographic)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))

    # 4. Randomly darken (night/overcast) or brighten (sunny)
    brightness_factor = float(rng.uniform(0.75, 1.25))
    img = ImageEnhance.Brightness(img).enhance(brightness_factor)

    # 5. Slight contrast boost
    img = ImageEnhance.Contrast(img).enhance(float(rng.uniform(1.0, 1.4)))

    return img


def main():
    print(f"Generating {len(SEED_REPORTS)} synthetic pothole images → {OUTPUT_DIR}")
    for i, (filename, severity, road_name) in enumerate(SEED_REPORTS):
        dest = OUTPUT_DIR / filename
        img = generate_pothole_image(severity, seed=i + 42, road_name=road_name)
        img.save(dest, format="JPEG", quality=90)
        size_kb = dest.stat().st_size // 1024
        print(f"  [{i+1:02d}] {filename}  severity={severity:<8}  {size_kb}KB  — {road_name}")
    print(f"\n✅ Done. Images saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
