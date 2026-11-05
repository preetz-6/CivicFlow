"""LLM adapter with record/replay.

AGENT_MODE=live    -> call Claude
AGENT_MODE=record  -> call Claude and save each request/response under agent_cache/<agent>/<key>.json
AGENT_MODE=replay  -> serve saved responses; a miss raises CacheMiss (the runtime then uses rules)
AGENT_MODE=rules   -> never call a model

The cache key hashes the full request (agent, model, system, tool names, messages incl. tool results),
i.e. one entry per TURN of the tool-use loop. Replay therefore needs a deterministic seed + clock.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

log = logging.getLogger("civicflow.llm")


class LLMUnavailable(Exception):
    pass


class CacheMiss(LLMUnavailable):
    pass


@dataclass
class LLMResult:
    content: list[dict]  # assistant content blocks as plain dicts (thinking blocks kept verbatim)
    stop_reason: str
    model: str
    source: str  # "live" | "replay"
    usage: dict | None = None


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def cache_key(agent: str, model: str, system: str, tools: list[dict], messages: list) -> str:
    payload = {"agent": agent, "model": model, "system": system, "tools": sorted(t["name"] for t in tools),
               "messages": messages}
    return hashlib.sha256(_canon(payload).encode()).hexdigest()[:40]


class LLMClient:
    def __init__(self) -> None:
        self._client = None
        self._fallbacks_ok = True

    @property
    def mode(self) -> str:
        return settings.agent_mode

    def available(self) -> bool:
        if self.mode == "rules":
            return False
        if self.mode == "replay":
            return True
        return bool(settings.anthropic_api_key)

    def _sdk(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=1)
        return self._client

    def _path(self, agent: str, key: str) -> Path:
        return Path(settings.agent_cache_dir) / agent / f"{key}.json"

    def create(self, *, agent: str, system: str, tools: list[dict], messages: list, max_tokens: int = 4096,
               timeout_s: float = 30.0) -> LLMResult:
        model = settings.civicflow_llm_model
        key = cache_key(agent, model, system, tools, messages)
        p = self._path(agent, key)
        if self.mode == "replay":
            if not p.exists():
                raise CacheMiss(f"no recorded response for {agent} turn {key}")
            d = json.loads(p.read_text(encoding="utf-8"))
            return LLMResult(d["content"], d["stop_reason"], d["model"], "replay", d.get("usage"))
        if not self.available():
            raise LLMUnavailable("no API key configured")
        res = self._call(model, system, tools, messages, max_tokens, timeout_s)
        if self.mode == "record":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_canon({"content": res.content, "stop_reason": res.stop_reason, "model": res.model,
                                 "usage": res.usage}), encoding="utf-8")
        return res

    def _call(self, model, system, tools, messages, max_tokens, timeout_s) -> LLMResult:
        import anthropic

        client = self._sdk().with_options(timeout=timeout_s)
        kwargs = dict(model=model, max_tokens=max_tokens, system=system, messages=messages,
                      output_config={"effort": "medium"})
        if tools:
            kwargs["tools"] = tools
        try:
            if self._fallbacks_ok:
                # Server-side refusal fallback (Claude API): on a policy decline the API re-runs on another model.
                resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
            else:
                resp = client.messages.create(**kwargs)
        except anthropic.BadRequestError as e:
            if self._fallbacks_ok and "fallback" in str(e).lower():
                log.warning("server-side fallbacks not accepted here; retrying without: %s", e)
                self._fallbacks_ok = False
                resp = client.messages.create(**kwargs)
            else:
                raise
        content = [b.model_dump(mode="json", exclude_none=True) for b in resp.content]
        usage = resp.usage.model_dump(mode="json") if getattr(resp, "usage", None) else None
        return LLMResult(content, resp.stop_reason, resp.model, "live", usage)


llm = LLMClient()


def text_of(content: list[dict]) -> str:
    return "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
