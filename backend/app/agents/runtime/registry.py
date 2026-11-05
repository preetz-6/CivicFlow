"""Wires deterministic handlers and every agent's triggers to the event bus / scheduler."""
from __future__ import annotations

import logging

from app.core.bus import Event, bus

log = logging.getLogger("civicflow.agents")
_registered = False
AGENTS: dict = {}


def agent_handler(agent):
    def handle(ev: Event) -> None:
        from app.agents.runtime.loop import run_agent

        run_agent(agent, ev.name, ev.payload)

    handle.__name__ = f"run_{agent.name}"
    return handle


def register_agents() -> None:
    from app.agents.auditor import auditor
    from app.agents.investigator import investigator

    for a in (investigator, auditor):
        AGENTS[a.name] = a
        for trig in a.triggers:
            bus.subscribe(trig, agent_handler(a))


def register_all() -> None:
    global _registered
    if _registered:
        return
    _registered = True
    from app.modules.complaints import handlers as complaint_handlers

    complaint_handlers.register()
    from app.modules.sla import engine as sla_engine

    sla_engine.register()
    from app import scheduler
    from app.modules.system import clock_state

    scheduler.add_job("clock_sync", clock_state.sync, 5)
    register_agents()
    log.info("handlers and agents registered: %s", ", ".join(AGENTS))
