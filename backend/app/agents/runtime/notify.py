"""Shared tool used by every agent: tell the citizen what is happening and why (simulated SMS outbox)."""
from app.agents.runtime.tools import props, tool
from app.models import ServiceRequest
from app.modules.notifications.service import TEMPLATES, notify_citizen as _notify


@tool(
    "notify_citizen",
    "Send a short, polite, plain-language update to every citizen who reported this grievance, in their own "
    "language (English/Kannada). Pick a template event; for DELAY give the honest reason in 'reason' "
    "(and 'reason_kn' in Kannada if you can). Idempotent per (grievance, event, dedupe).",
    {
        "properties": props(
            sr_id="string",
            event={"type": "string", "enum": sorted(TEMPLATES)},
            reason=("string", "Plain-language reason, for DELAY / REJECTED"),
            reason_kn=("string", "Same reason in Kannada (optional)"),
            dedupe=("string", "Optional key so the same update is not sent twice"),
        ),
        "required": ["sr_id", "event"],
    },
)
def notify_citizen_tool(ctx, sr_id: str, event: str, reason: str | None = None, reason_kn: str | None = None,
                        dedupe: str | None = None):
    sr = ctx.db.get(ServiceRequest, sr_id)
    if sr is None:
        return {"error": f"no grievance {sr_id}"}
    ids = _notify(ctx.db, sr, event, {"reason": reason, "reason_kn": reason_kn or reason}, dedupe=dedupe)
    return {"sent": len(ids), "event": event}
