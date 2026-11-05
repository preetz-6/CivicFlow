"""Wires each agent's triggers to the event bus / scheduler. Agents register here in C2/C3."""
import logging

log = logging.getLogger("civicflow.agents")
_registered = False


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
    log.info("handlers registered")
