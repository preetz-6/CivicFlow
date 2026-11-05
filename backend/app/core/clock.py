"""The one clock. Every timestamp and SLA computation goes through `clock.now()`.

Simulated time = sim_origin + (real_now - real_origin) * scale.
Tests freeze it; the demo jumps it forward with `advance()`.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


class Clock:
    def __init__(self, scale: float = 1.0, sim_origin: datetime | None = None):
        self._lock = threading.Lock()
        self.scale = scale
        self._real_origin = time.time()
        self._sim_origin = sim_origin or datetime.now(timezone.utc)
        self._frozen: datetime | None = None

    def now(self) -> datetime:
        with self._lock:
            if self._frozen is not None:
                return self._frozen
            elapsed = (time.time() - self._real_origin) * self.scale
            return (self._sim_origin + timedelta(seconds=elapsed)).astimezone(IST)

    def configure(self, scale: float, sim_origin: datetime) -> None:
        with self._lock:
            self.scale = scale
            self._sim_origin = sim_origin
            self._real_origin = time.time()
            self._frozen = None

    def freeze(self, at: datetime | None = None) -> None:
        current = at or self.now()
        with self._lock:
            self._frozen = current

    def unfreeze(self) -> None:
        current = self.now()
        with self._lock:
            self._frozen = None
            self._sim_origin = current
            self._real_origin = time.time()

    def advance(self, delta: timedelta) -> datetime:
        with self._lock:
            if self._frozen is not None:
                self._frozen = self._frozen + delta
                return self._frozen
            self._sim_origin = self._sim_origin + delta
        return self.now()

    @property
    def frozen(self) -> bool:
        return self._frozen is not None

    def state(self) -> dict:
        return {"now": self.now().isoformat(), "scale": self.scale, "frozen": self.frozen}

    # Persisted in system_state so a uvicorn --reload does not rewind simulated time.
    def dump(self) -> dict:
        with self._lock:
            return {
                "scale": self.scale,
                "real_origin": self._real_origin,
                "sim_origin": self._sim_origin.isoformat(),
                "frozen": self._frozen.isoformat() if self._frozen else None,
            }

    def load(self, d: dict) -> None:
        with self._lock:
            self.scale = float(d["scale"])
            self._real_origin = float(d["real_origin"])
            self._sim_origin = datetime.fromisoformat(d["sim_origin"])
            self._frozen = datetime.fromisoformat(d["frozen"]) if d.get("frozen") else None


clock = Clock()


def now() -> datetime:
    return clock.now()


def sla_hours_to_real_seconds(hours: float) -> float:
    return hours * 3600 / max(clock.scale, 1e-9)
