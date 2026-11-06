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
    return {"ok": True, "agent_mode": settings.agent_mode, "llm": settings.llm_enabled,
            "llm_provider": settings.llm_provider, "llm_model": settings.llm_model, **clock.state()}


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


@router.post("/demo/run/{agent}")
def demo_run(agent: str):
    """DEMO ONLY: run a scheduled agent now (sensing). Event-driven agents run by themselves."""
    if not settings.demo_mode:
        raise HTTPException(404)
    import threading

    if agent == "sensing":
        from app.agents.sensing import run_sensing

        job = lambda: run_sensing(force=True)  # noqa: E731
    elif agent == "surge":
        from app.agents.surge import run_surge_check

        job = lambda: run_surge_check(force=True)  # noqa: E731
    elif agent == "followup":
        from app.agents.followup import run_followup_timer
        from app.modules.sla.engine import run_sweep

        def job():
            run_sweep()
            run_followup_timer()
    else:
        raise HTTPException(404, "Unknown scheduled agent")
    # Model calls can take minutes on a rate-limited tier: start the run and return at once.
    # Progress shows in the Agent Activity Log (status RUNNING -> OK / FALLBACK).
    threading.Thread(target=job, name=f"demo-{agent}", daemon=True).start()
    return {"started": True, "run_id": None, "agent": agent}


class AdvanceIn(BaseModel):
    hours: float


@router.post("/demo/clock/realtime", response_model=ClockOut)
def realtime_clock(db: Session = Depends(get_db)):
    """Set the SLA clock to the real date and time, running at normal speed (x1). Jumps: /demo/clock/advance."""
    from datetime import datetime, timezone

    if not settings.demo_mode:
        raise HTTPException(404)
    clock.configure(1.0, datetime.now(timezone.utc))
    clock_state.save(db)
    db.commit()
    return clock.state()


@router.post("/demo/clock/pause", response_model=ClockOut)
def pause_clock(db: Session = Depends(get_db)):
    """Stop the SLA clock (e.g. right after reseeding, so the data stays fresh until the presentation)."""
    if not settings.demo_mode:
        raise HTTPException(404)
    if not clock.frozen:
        clock.freeze()
        clock_state.save(db)
        db.commit()
    return clock.state()


@router.post("/demo/clock/resume", response_model=ClockOut)
def resume_clock(db: Session = Depends(get_db)):
    if not settings.demo_mode:
        raise HTTPException(404)
    if clock.frozen:
        clock.unfreeze()
        clock_state.save(db)
        db.commit()
    return clock.state()


@router.post("/demo/clock/advance", response_model=ClockOut)
def advance(body: AdvanceIn, db: Session = Depends(get_db)):
    if not settings.demo_mode:
        raise HTTPException(404)
    clock.advance(timedelta(hours=body.hours))
    clock_state.save(db)
    db.commit()
    return clock.state()
