"""In-process event bus.

publish() stores the event in the `events` table in the caller's transaction and
queues it on the session. Handlers run only after that transaction commits
(and never if it rolls back), on a thread pool, each with its own DB session.
Tests set `bus.sync = True` so handlers run inline right after commit.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from app.core.clock import now

log = logging.getLogger("civicflow.bus")


@dataclass
class Event:
    id: int | None
    name: str
    payload: dict[str, Any]


Handler = Callable[[Event], None]


class Bus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bus")
        self.sync = False
        self.enabled = True

    def subscribe(self, name: str, handler: Handler) -> None:
        if handler not in self._handlers[name]:
            self._handlers[name].append(handler)

    def on(self, *names: str) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            for n in names:
                self.subscribe(n, fn)
            return fn

        return deco

    def clear(self) -> None:
        self._handlers.clear()

    def publish(self, session: Session, name: str, payload: dict[str, Any]) -> None:
        from app.models.audit import EventRow

        row = EventRow(name=name, payload=payload, at=now())
        session.add(row)
        session.flush()
        session.info.setdefault("pending_events", []).append(Event(row.id, name, payload))

    def dispatch(self, ev: Event) -> None:
        if not self.enabled:
            return
        handlers = list(self._handlers.get(ev.name, [])) + list(self._handlers.get("*", []))
        for h in handlers:
            if self.sync:
                self._run(h, ev)
            else:
                self._pool.submit(self._run, h, ev)

    @staticmethod
    def _run(h: Handler, ev: Event) -> None:
        try:
            h(ev)
        except Exception:  # a bad handler must never break the publisher
            log.exception("handler %s failed for %s", getattr(h, "__name__", h), ev.name)


bus = Bus()


@sa_event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    pending = session.info.pop("pending_events", [])
    for ev in pending:
        bus.dispatch(ev)


@sa_event.listens_for(Session, "after_soft_rollback")
def _after_rollback(session: Session, previous_transaction) -> None:
    session.info.pop("pending_events", None)
