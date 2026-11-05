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
        tx = session.get_nested_transaction() or session.get_transaction()
        session.info.setdefault("pending_events", []).append((tx, Event(row.id, name, payload)))

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
    # SQLAlchemy also fires after_commit when a SAVEPOINT is released; only the outermost commit
    # makes the data visible to other sessions, so only then do handlers run.
    if session.in_nested_transaction():
        return
    pending = session.info.pop("pending_events", [])
    for _tx, ev in pending:
        bus.dispatch(ev)


def _within(tx, target) -> bool:
    while tx is not None:
        if tx is target:
            return True
        tx = tx.parent
    return False


@sa_event.listens_for(Session, "after_soft_rollback")
def _after_rollback(session: Session, previous_transaction) -> None:
    # Drop only events published inside the transaction / savepoint that rolled back.
    pending = session.info.get("pending_events")
    if not pending:
        return
    keep = [(tx, ev) for tx, ev in pending if not _within(tx, previous_transaction)]
    if keep:
        session.info["pending_events"] = keep
    else:
        session.info.pop("pending_events", None)
