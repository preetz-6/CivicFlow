"""Photo ingest: keep the original bytes (EXIF intact), extract GPS/time, sha256 and perceptual hash."""
from __future__ import annotations

import hashlib
import io
from datetime import datetime

import imagehash
import piexif
from PIL import Image
from sqlalchemy.orm import Session

from app.adapters.storage import signed_url, storage
from app.core.clock import IST, now
from app.core.errors import DomainError
from app.models import Attachment

MAX_BYTES = 12 * 1024 * 1024
ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _rational(v) -> float:
    return v[0] / v[1] if v[1] else 0.0


def _dms(vals, ref) -> float:
    d, m, s = (_rational(x) for x in vals)
    out = d + m / 60 + s / 3600
    return -out if ref in (b"S", b"W", "S", "W") else out


def read_exif(data: bytes) -> dict:
    """Returns {lat, lon, time} (any may be None). Never raises."""
    out = {"lat": None, "lon": None, "time": None}
    try:
        ex = piexif.load(data)
    except Exception:
        return out
    gps = ex.get("GPS") or {}
    try:
        if piexif.GPSIFD.GPSLatitude in gps and piexif.GPSIFD.GPSLongitude in gps:
            out["lat"] = round(_dms(gps[piexif.GPSIFD.GPSLatitude], gps.get(piexif.GPSIFD.GPSLatitudeRef, b"N")), 7)
            out["lon"] = round(_dms(gps[piexif.GPSIFD.GPSLongitude], gps.get(piexif.GPSIFD.GPSLongitudeRef, b"E")), 7)
    except Exception:
        pass
    raw = (ex.get("Exif") or {}).get(piexif.ExifIFD.DateTimeOriginal) or (ex.get("0th") or {}).get(piexif.ImageIFD.DateTime)
    if raw:
        try:
            t = datetime.strptime(raw.decode() if isinstance(raw, bytes) else raw, "%Y:%m:%d %H:%M:%S")
            out["time"] = t.replace(tzinfo=IST)  # phone cameras write local time; demo city is IST
        except Exception:
            pass
    return out


def _deg_to_rational(deg: float):
    deg = abs(deg)
    d = int(deg)
    m_f = (deg - d) * 60
    m = int(m_f)
    s = round((m_f - m) * 60 * 10000)
    return ((d, 1), (m, 1), (s, 10000))


def write_exif(data: bytes, lat: float | None, lon: float | None, t: datetime | None) -> bytes:
    """Used by the demo photo endpoint and tests to stamp fixture photos."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
    if t is not None:
        s = t.astimezone(IST).strftime("%Y:%m:%d %H:%M:%S").encode()
        exif["0th"][piexif.ImageIFD.DateTime] = s
        exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = s
    if lat is not None and lon is not None:
        exif["GPS"] = {
            piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S", piexif.GPSIFD.GPSLatitude: _deg_to_rational(lat),
            piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W", piexif.GPSIFD.GPSLongitude: _deg_to_rational(lon),
        }
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88, exif=piexif.dump(exif))
    return buf.getvalue()


def phash_of(data: bytes) -> str | None:
    try:
        return str(imagehash.phash(Image.open(io.BytesIO(data))))
    except Exception:
        return None


def store_photo(db: Session, data: bytes, content_type: str, *, kind: str, uploaded_by: int | None,
                sr_id: str | None = None, wo_id: str | None = None) -> Attachment:
    if len(data) > MAX_BYTES:
        raise DomainError("Photo is larger than 12 MB")
    ext = ALLOWED.get(content_type or "")
    if ext is None:
        try:
            fmt = Image.open(io.BytesIO(data)).format
        except Exception:
            raise DomainError("File is not a supported image (JPEG/PNG/WebP)")
        ext, content_type = {"JPEG": (".jpg", "image/jpeg"), "PNG": (".png", "image/png"),
                             "WEBP": (".webp", "image/webp")}.get(fmt, (None, None))
        if ext is None:
            raise DomainError("File is not a supported image (JPEG/PNG/WebP)")
    meta = read_exif(data)
    att = Attachment(
        sr_id=sr_id, wo_id=wo_id, kind=kind, path=storage.save(data, ext), content_type=content_type,
        sha256=hashlib.sha256(data).hexdigest(), phash=phash_of(data), exif_lat=meta["lat"], exif_lon=meta["lon"],
        exif_time=meta["time"], uploaded_by=uploaded_by, uploaded_at=now(),
    )
    db.add(att)
    db.flush()
    return att


def attachment_out(a: Attachment) -> dict:
    return {
        "id": a.id, "kind": a.kind, "url": signed_url(a.id), "uploaded_at": a.uploaded_at,
        "exif_lat": a.exif_lat, "exif_lon": a.exif_lon, "exif_time": a.exif_time, "wo_id": a.wo_id,
    }
