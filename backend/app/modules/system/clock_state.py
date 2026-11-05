"""Persist the simulated clock so `uvicorn --reload` never rewinds time."""
from app.config import settings
from app.core.clock import clock
from app.core.db import session_scope
from app.models import SystemState

KEY = "clock"


def restore_or_init() -> None:
    with session_scope() as db:
        row = db.get(SystemState, KEY)
        if row:
            clock.load(row.value)
            return
        reset(db)


def reset(db, at=None) -> None:
    from datetime import datetime, timezone

    origin = at or (settings.demo_epoch if settings.demo_mode else datetime.now(timezone.utc))
    clock.configure(settings.time_scale, origin)
    save(db)


def save(db) -> None:
    row = db.get(SystemState, KEY)
    if row:
        row.value = clock.dump()
    else:
        db.add(SystemState(key=KEY, value=clock.dump()))
