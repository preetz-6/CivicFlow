"""run_agent(): the shared tool-use loop + decision log + fallback.

1. build_input; open an agent_runs row (committed immediately so the Activity Log shows RUNNING)
2. if an LLM is available: call Claude with the agent's tools, execute requested tools (each logged
   as an agent_steps row), loop until a final answer or max_steps / timeout
3. parse the final JSON, validate with the agent's Pydantic model; on failure retry once with the
   validation errors; still invalid -> fallback
4. any LLM error / timeout / refusal / cache miss / no key -> agent.fallback() (model = "rules")
5. agent.apply(validated output): deterministic side effects, inside the same transaction
6. finish the run row: status, model, latency, output, decision, rationale, confidence
"""
from __future__ import annotations

import json
import logging
import re
import time

from pydantic import BaseModel, ValidationError

from app.adapters.llm import LLMUnavailable, llm, text_of
from app.config import settings
from app.agents.runtime.base import Agent
from app.agents.runtime.tools import REGISTRY, ToolContext, invoke
from app.core.actor import Actor
from app.core.clock import now
from app.core.db import SessionLocal
from app.models import AgentRun

log = logging.getLogger("civicflow.agents")


class AgentFailed(Exception):
    pass


def extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in final answer")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("final answer is not a JSON object")
    return obj


def _llm_run(agent: Agent, ctx: ToolContext, inp: dict, deadline: float) -> tuple[BaseModel, str]:
    tools = [REGISTRY[n].api_def() for n in agent.tools]
    system = agent.full_system()
    messages: list = [{"role": "user", "content": agent.render_input(inp)}]
    retried = False
    model_used = None
    for _step in range(agent.max_steps + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            raise AgentFailed("timeout")
        res = llm.create(agent=agent.name, system=system, tools=tools, messages=messages,
                         max_tokens=agent.max_tokens, timeout_s=remaining)
        model_used = f"replay:{res.model}" if res.source == "replay" else res.model
        if res.stop_reason == "refusal":
            raise AgentFailed("model declined (refusal)")
        if res.stop_reason == "max_tokens":
            raise AgentFailed("output truncated (max_tokens)")
        messages.append({"role": "assistant", "content": res.content})
        if res.stop_reason == "pause_turn":
            continue
        tool_uses = [b for b in res.content if b.get("type") == "tool_use"]
        if tool_uses:
            results = []
            for b in tool_uses:
                if b["name"] not in agent.tools:
                    out = {"error": f"tool {b['name']} is not available to this agent"}
                else:
                    out = invoke(ctx, b["name"], b.get("input") or {})
                results.append({"type": "tool_result", "tool_use_id": b["id"],
                                "content": json.dumps(out, ensure_ascii=False, default=str),
                                **({"is_error": True} if isinstance(out, dict) and "error" in out else {})})
            messages.append({"role": "user", "content": results})
            continue
        try:
            return agent.output_model.model_validate(extract_json(text_of(res.content))), model_used
        except (ValueError, ValidationError) as e:
            if retried:
                raise AgentFailed(f"invalid final output after retry: {e}") from e
            retried = True
            messages.append({"role": "user", "content": (
                "Your final answer did not validate. Errors:\n" + str(e)[:1500] +
                "\nReply again with ONLY the corrected JSON object.")})
    raise AgentFailed(f"step limit ({agent.max_steps}) reached")


def run_agent(agent: Agent, trigger: str, payload: dict) -> int | None:
    """Returns the agent_runs.id, or None if the agent decided there was nothing to do."""
    db = SessionLocal()
    t0 = time.monotonic()
    try:
        inp = agent.build_input(db, payload)
        if inp is None:
            db.commit()  # build_input may do deterministic prep work (e.g. re-clustering)
            return None
        run = AgentRun(agent=agent.name, trigger=trigger, subject_type=agent.subject_type,
                       subject_id=agent.subject_id(inp), status="RUNNING",
                       input_summary=json.loads(json.dumps({k: v for k, v in inp.items() if not k.startswith("_")},
                                                           default=str)),
                       started_at=now())
        db.add(run)
        db.commit()
        ctx = ToolContext(db=db, run_id=run.id, agent=agent.name, actor=Actor.agent(agent.name),
                          subject_id=run.subject_id, live=True)
        out: BaseModel | None = None
        error = None
        model = "rules"
        if llm.available() and not settings.model_allowed(agent.name):
            error = f"rule-based by design (LLM_AGENTS={settings.llm_agents}: the model is kept for those agents)"
        elif llm.available() and agent.use_llm(inp, getattr(llm, "mode", "live")):
            try:
                budget = agent.timeout_s * (10 if getattr(llm, "mode", "live") == "record" else 1)  # recording may wait out rate limits
                out, model = _llm_run(agent, ctx, inp, t0 + budget)
            except (LLMUnavailable, AgentFailed) as e:
                error = str(e)
            except Exception as e:  # network, API status, anything: never break the pipeline
                error = f"{type(e).__name__}: {e}"
                log.warning("agent %s LLM path failed: %s", agent.name, error)
        elif llm.available():
            error = "rule-based by design for this case (model quota reserved for the demo's key runs)"
        else:
            error = "LLM not configured (AGENT_MODE=rules or no API key)"
        status = "OK"
        if out is None:
            out = agent.fallback(ctx, inp)
            model, status = "rules", "FALLBACK"
        try:
            with db.begin_nested():
                agent.apply(ctx, inp, out)
        except Exception as e:
            log.exception("agent %s apply failed", agent.name)
            status, error = "ERROR", f"apply failed: {type(e).__name__}: {e}"
        run.status = status
        run.model = model
        run.output = json.loads(out.model_dump_json())
        run.decision = (agent.decision(out) or "")[:160]
        run.rationale = agent.rationale(out)
        run.confidence = agent.confidence(out)
        run.error = error
        run.latency_ms = int((time.monotonic() - t0) * 1000)
        run.finished_at = now()
        db.commit()
        return run.id
    except Exception:
        db.rollback()
        log.exception("agent %s crashed on %s", agent.name, trigger)
        return None
    finally:
        db.close()
