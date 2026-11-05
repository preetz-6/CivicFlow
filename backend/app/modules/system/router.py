from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import clock
from app.core.db import get_db
from app.modules.system import clock_state
from app.schemas.common import ClockOut

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True, "agent_mode": settings.agent_mode, "llm": settings.llm_enabled, **clock.state()}


@router.get("/clock", response_model=ClockOut)
def get_clock():
    return clock.state()


@router.get("/demo/points")
def demo_points():
    """Coordinates the simulator uses (true potholes, speed breakers, rain areas)."""
    from app.seed.geo import demo_points as pts

    return pts()


@router.get("/demo/photos/{variant}.jpg")
def demo_photo(variant: str, wo_id: str, db: Session = Depends(get_db)):
    """DEMO ONLY. Variants: before | after_good | after_far | after_old | after_noexif | after_reused.
    Download, then upload via the Field Team screen so the real audit pipeline runs."""
    from fastapi.responses import Response
    from sqlalchemy import select

    from app.adapters.storage import storage
    from app.models import Attachment, ServiceRequest, WorkOrder
    from app.modules import geo
    from app.modules.system import demo_photos

    if not settings.demo_mode or variant not in demo_photos.VARIANTS:
        raise HTTPException(404)
    wo = db.get(WorkOrder, wo_id)
    if wo is None:
        raise HTTPException(404, "Unknown work order")
    sr = db.get(ServiceRequest, wo.sr_id)
    reuse = None
    if variant == "after_reused":  # a photo from ANOTHER job (or this job's before-photo)
        a = db.scalar(select(Attachment).where(Attachment.wo_id != wo.id, Attachment.wo_id.is_not(None))
                      .order_by(Attachment.id.desc()).limit(1)) or db.scalar(
            select(Attachment).where(Attachment.wo_id == wo.id, Attachment.kind == "BEFORE").limit(1))
        reuse = storage.read(a.path) if a else None
    data = demo_photos.make(variant, wo_id=wo.id, category=sr.category, site=geo.latlon(sr.location),
                            assigned_at=wo.assigned_at, reuse_bytes=reuse)
    return Response(data, media_type="image/jpeg",
                    headers={"Content-Disposition": f'attachment; filename="{wo.id}-{variant}.jpg"'})


class AdvanceIn(BaseModel):
    hours: float


@router.post("/demo/clock/advance", response_model=ClockOut)
def advance(body: AdvanceIn, db: Session = Depends(get_db)):
    if not settings.demo_mode:
        raise HTTPException(404)
    clock.advance(timedelta(hours=body.hours))
    clock_state.save(db)
    db.commit()
    return clock.state()
