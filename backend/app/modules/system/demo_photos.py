"""DEMO ONLY: hand the presenter a photo for a work order, with EXIF stamped NOW at (or away from) the site.

The presenter downloads it and uploads it through the normal Field Team upload, so the real EXIF /
hash / audit pipeline runs. If real phone photos exist in app/seed/fixtures/ they are used:
  pothole_before.jpg, pothole_after.jpg, pothole_far.jpg (a DIFFERENT place), streetlight_before.jpg, ...
otherwise a synthetic image is drawn.
"""
from __future__ import annotations

import io
import random
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.core.clock import now
from app.modules.media.service import write_exif

FIXTURES = Path(__file__).resolve().parents[2] / "seed" / "fixtures"
VARIANTS = ("before", "after_good", "after_far", "after_old", "after_noexif", "after_reused")


def _synthetic(kind: str, seed: str) -> bytes:
    rng = random.Random(seed)
    w, h = 960, 720
    img = Image.new("RGB", (w, h), (88, 88, 86))
    d = ImageDraw.Draw(img)
    for _ in range(9000):  # asphalt grain
        x, y = rng.randrange(w), rng.randrange(h)
        g = rng.randint(55, 125)
        d.point((x, y), fill=(g, g, g - 3))
    for _ in range(7):  # large shadows / kerb / wall shapes: distinct low-frequency structure per photo
        x0, y0 = rng.randrange(-200, w), rng.randrange(-200, h)
        x1, y1 = x0 + rng.randint(150, 520), y0 + rng.randint(120, 420)
        g = rng.choice([rng.randint(20, 50), rng.randint(140, 200)])
        (d.ellipse if rng.random() < 0.5 else d.rectangle)([x0, y0, x1, y1], fill=(g, g, g - 4))
    y_l = rng.uniform(0.6, 0.95)
    d.line([(0, h * y_l), (w, h * (y_l + rng.uniform(-0.2, 0.2)))], fill=(225, 225, 210), width=10)  # lane edge
    cx, cy = w // 2 + rng.randint(-60, 60), h // 2 + rng.randint(-40, 40)
    if kind == "before":
        pts = [(cx + rng.randint(-200, 200) * abs(__import__("math").cos(a / 3)), cy + rng.randint(-110, 110))
               for a in range(14)]
        d.polygon(pts, fill=(38, 34, 30))
        d.ellipse([cx - 120, cy - 50, cx + 110, cy + 60], fill=(30, 27, 24))
        d.ellipse([cx - 70, cy - 20, cx + 60, cy + 30], fill=(70, 80, 90))  # water in the pit
    else:
        d.rounded_rectangle([cx - 190, cy - 100, cx + 190, cy + 100], radius=18, fill=(46, 46, 48))  # fresh patch
        for _ in range(2500):
            x, y = rng.randint(cx - 185, cx + 185), rng.randint(cy - 95, cy + 95)
            g = rng.randint(30, 62)
            d.point((x, y), fill=(g, g, g))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _base(category: str, kind: str, seed: str, fixture: str | None = None) -> bytes:
    stem = "streetlight" if category == "STREETLIGHT" else "pothole"
    f = FIXTURES / f"{stem}_{fixture or ('before' if kind == 'before' else 'after')}.jpg"
    return f.read_bytes() if f.exists() else _synthetic(kind, seed)


def make(variant: str, *, wo_id: str, category: str, site: tuple[float, float], assigned_at,
         reuse_bytes: bytes | None = None) -> bytes:
    lat, lon = site
    t = now()
    if variant == "before":
        return write_exif(_base(category, "before", wo_id), lat, lon, t)
    if variant == "after_good":
        return write_exif(_base(category, "after", wo_id + "-good"), lat + 0.00008, lon + 0.00005, t)
    if variant == "after_far":  # ~2.1 km north-east of the site
        return write_exif(_base(category, "after", wo_id + "-far", "far"), lat + 0.013, lon + 0.014, t)
    if variant == "after_old":  # taken two days before the job was assigned
        return write_exif(_base(category, "after", wo_id + "-old"), lat, lon, assigned_at - timedelta(days=2))
    if variant == "after_noexif":
        img = Image.open(io.BytesIO(_base(category, "after", wo_id + "-noexif"))).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return buf.getvalue()
    if variant == "after_reused":
        return write_exif(reuse_bytes or _base(category, "before", wo_id), lat, lon, t)
    raise ValueError(variant)
