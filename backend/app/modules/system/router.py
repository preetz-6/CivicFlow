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
