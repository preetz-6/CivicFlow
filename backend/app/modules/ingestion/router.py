"""Ingestion API (partner contract: docs/API.md). Auth: per-source X-API-Key. Idempotency-Key replays the
original response for a retried batch."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Body, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.db import get_db
from app.core.security import hash_api_key
from app.models import DataSource, IngestIdempotency
from app.modules.ingestion.service import MAX_BATCH, ingest

router = APIRouter(prefix="/ingest", tags=["ingestion"])


def source_for(db: Session, key: str | None) -> DataSource:
    if not key:
        raise HTTPException(401, "X-API-Key header required")
    src = db.scalar(select(DataSource).where(DataSource.api_key_hash == hash_api_key(key)))
    if src is None:
        raise HTTPException(401, "Unknown API key")
    return src


def _run(db: Session, src: DataSource, records: list, idem: str | None) -> dict:
    if len(records) > MAX_BATCH:
        raise HTTPException(413, f"Batch too large: {len(records)} records (max {MAX_BATCH})")
    key = f"{src.id}:{idem}" if idem else None
    if key:
        prev = db.get(IngestIdempotency, key[:96])
        if prev:
            return {**prev.response, "idempotent_replay": True}
    result = ingest(db, src, records)
    if key:
        db.add(IngestIdempotency(key=key[:96], response=result, at=now()))
    db.commit()
    return result


@router.post("/detections")
def post_detections(
    body: list | dict = Body(..., examples=[[{
        "source_record_id": "oem-sim-000123", "lat": 12.9081, "lon": 77.4874, "hazard_type": "POTHOLE",
        "detected_at": "2026-11-05T09:12:44+05:30", "confidence": 0.82, "speed_kmph": 32,
        "vertical_accel_peak_g": 1.9, "vehicle_ref": "salted-hash-rotated-daily", "image_url": None}]]),
    x_api_key: str | None = Header(None), idempotency_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """JSON batch of up to 1000 records: a bare array, or {"records": [...]}."""
    src = source_for(db, x_api_key)
    records = body.get("records") if isinstance(body, dict) else body
    if not isinstance(records, list):
        raise HTTPException(422, 'Body must be an array of records or {"records": [...]}')
    return _run(db, src, records, idempotency_key)


@router.post("/detections/csv")
async def post_csv(file: UploadFile = File(...), x_api_key: str | None = Header(None),
                   idempotency_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Bulk import. Columns: source_record_id, lat, lon, hazard_type, detected_at, confidence, speed_kmph,
    vertical_accel_peak_g, vehicle_ref, image_url."""
    src = source_for(db, x_api_key)
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    records = [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
               for row in csv.DictReader(io.StringIO(text))]
    return _run(db, src, records, idempotency_key)
