"""Tool registry. Tools are plain Python functions over the DB / adapters that return SMALL JSON.

    @tool("get_ward_for_location", "Which ward contains a point", {...json schema...})
    def get_ward_for_location(ctx, lat, lon): ...

Every invocation (by the model OR by a rule-based fallback) is logged as an agent_steps row.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.clock import now
from app.models import AgentStep


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict
    fn: Callable[..., Any]

    def api_def(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, description: str, schema: dict):
    schema = {"type": "object", "additionalProperties": False, **schema}
    schema.setdefault("properties", {})
    schema.setdefault("required", [])

    def deco(fn):
        REGISTRY[name] = ToolSpec(name, description, schema, fn)
        return fn

    return deco


def props(**kw) -> dict:
    """Shorthand: props(lat="number", lon="number", radius_m=("number", "metres")) -> JSON-schema properties."""
    out = {}
    for k, v in kw.items():
        if isinstance(v, tuple):
            t, desc = v
            out[k] = {"type": t, "description": desc}
        elif isinstance(v, dict):
            out[k] = v
        else:
            out[k] = {"type": v}
    return out


@dataclass
class ToolContext:
    db: Session
    run_id: int
    agent: str
    actor: Actor
    subject_id: str | None = None
    step: int = 0
    live: bool = False  # set by run_agent: commit read-only steps as they happen
    scratch: dict = field(default_factory=dict)  # tools may stash facts for apply()/fallback

    def call(self, name: str, args: dict | None = None, *, by: str = "model") -> Any:
        """Invoke a registered tool and log it. by='rules' marks fallback steps in the Activity Log."""
        return invoke(self, name, args or {}, by=by)


def _summ(obj: Any, limit: int = 3000) -> Any:
    s = json.dumps(obj, default=str)
    if len(s) <= limit:
        return json.loads(s)
    return {"truncated": True, "preview": s[:limit]}


def invoke(ctx: ToolContext, name: str, args: dict, *, by: str = "model") -> Any:
    spec = REGISTRY.get(name)
    t0 = time.perf_counter()
    err = None
    if spec is None:
        result: Any = {"error": f"unknown tool {name}"}
        err = result["error"]
    else:
        try:
            with ctx.db.begin_nested():
                result = spec.fn(ctx, **args)
        except TypeError as e:
            result, err = {"error": f"bad arguments: {e}"}, str(e)
        except Exception as e:  # tool errors go back to the model, never crash the run
            result, err = {"error": f"{type(e).__name__}: {e}"}, str(e)
    ctx.step += 1
    label = name if by == "model" else (f"action:{name}" if by == "apply" else f"rule:{name}")
    ctx.db.add(AgentStep(run_id=ctx.run_id, idx=ctx.step, tool=label,
                         args=_summ(args, 1000), result_summary=_summ(result), error=err,
                         latency_ms=int((time.perf_counter() - t0) * 1000), at=now()))
    ctx.db.flush()
    _publish_live(ctx, by)
    return result


def _publish_live(ctx: ToolContext, by: str) -> None:
    """Make lookup / check steps visible to the Agent Operations view while the run is still going.
    Only outside apply(): actions stay in one all-or-nothing transaction (apply runs inside a savepoint)."""
    if ctx.live and by != "apply" and not ctx.db.in_nested_transaction():
        ctx.db.commit()


def note(ctx: ToolContext, label: str, detail: Any) -> None:
    """Log a non-tool deterministic check (e.g. 'rule:priority_table') as a step."""
    ctx.step += 1
    ctx.db.add(AgentStep(run_id=ctx.run_id, idx=ctx.step, tool=f"rule:{label}", args=None,
                         result_summary=_summ(detail), at=now()))
    ctx.db.flush()
