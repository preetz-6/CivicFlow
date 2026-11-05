"""Agent base class. Subclasses declare:

  name, system_prompt, tools (registered tool names), triggers (bus event names),
  output_model (Pydantic), max_steps, timeout_s
  build_input(db, payload) -> dict | None   (None = nothing to do; no run is logged)
  fallback(ctx, inp) -> output_model        (rule-based; calls tools via ctx.call(..., by="rules"))
  apply(ctx, inp, out) -> None              (deterministic side effects from VALIDATED output)
  decision(out) -> str                      (one line for the Activity Log)
"""
from __future__ import annotations

import json
from typing import ClassVar

from pydantic import BaseModel

from app.agents.runtime.tools import ToolContext

COMMON_RULES = """You are an automated analyst inside CivicFlow, the grievance system of a municipal corporation in Bengaluru.
Ground rules:
- Use the tools to look things up; never invent IDs, places, counts or dates. If a tool returns nothing, say so.
- You only PROPOSE. Deterministic code and human officers make the binding decisions. You can never reject or close a complaint.
- Be concise. Rationale bullets are read by busy officers: short, factual, each one tied to a tool result.
- Call tools in parallel when they are independent.
- When finished, reply with ONLY one JSON object (no prose, no code fence) that validates against this JSON schema:
"""


class Agent:
    name: ClassVar[str]
    label: ClassVar[str]
    system_prompt: ClassVar[str]
    tools: ClassVar[list[str]] = []
    triggers: ClassVar[list[str]] = []
    output_model: ClassVar[type[BaseModel]]
    subject_type: ClassVar[str] = "SR"
    max_steps: ClassVar[int] = 8
    timeout_s: ClassVar[float] = 45.0
    max_tokens: ClassVar[int] = 6000

    def full_system(self) -> str:
        schema = json.dumps(self.output_model.model_json_schema(), separators=(",", ":"))
        return f"{self.system_prompt.strip()}\n\n{COMMON_RULES}{schema}"

    def build_input(self, db, payload: dict) -> dict | None:
        raise NotImplementedError

    def subject_id(self, inp: dict) -> str | None:
        return inp.get("subject_id")

    def render_input(self, inp: dict) -> str:
        body = {k: v for k, v in inp.items() if not k.startswith("_")}
        return "Analyse this case. Input:\n" + json.dumps(body, ensure_ascii=False, default=str, indent=1)

    def fallback(self, ctx: ToolContext, inp: dict) -> BaseModel:
        raise NotImplementedError

    def apply(self, ctx: ToolContext, inp: dict, out: BaseModel) -> None:
        pass

    def decision(self, out: BaseModel) -> str:
        return ""

    def rationale(self, out: BaseModel) -> str:
        r = getattr(out, "rationale", None)
        return "\n".join(f"- {x}" for x in r) if isinstance(r, list) else (r or "")

    def confidence(self, out: BaseModel) -> float | None:
        return getattr(out, "confidence", None)

    def use_llm(self, inp: dict, mode: str) -> bool:
        """Whether this run should use the model at all (rate-limited tiers record only the demo's key runs)."""
        return True
