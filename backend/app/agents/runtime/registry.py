"""Wires each agent's triggers to the event bus / scheduler. Agents register here in C2/C3."""
import logging

log = logging.getLogger("civicflow.agents")
_registered = False


def register_all() -> None:
    global _registered
    if _registered:
        return
    _registered = True
    log.info("agent registry: no agents registered yet (C1)")
