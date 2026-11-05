"""LLM adapter with record/replay.

AGENT_MODE=live    -> call Claude
AGENT_MODE=record  -> call Claude and save each request/response under agent_cache/<agent>/<key>.json
AGENT_MODE=replay  -> serve saved responses; a miss raises CacheMiss (the runtime then uses rules)
AGENT_MODE=rules   -> never call a model
LLM_PROVIDER=anthropic (default, Claude via the anthropic SDK) | gemini (Google Gemini via google-genai)

The cache key is (agent, model, prompt, tool names, normalised case input, turn number): see cache_key().
Replay therefore needs the same demo story (same texts / coordinates / simulator seeds), not the same clock.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
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


_TS = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:?\d{2}|Z)?")
_IDS = re.compile(r"(SR|WO)-[0-9]{4}-[0-9]{6}")
_FLOAT = re.compile(r"-?\d+\.\d{5,}")


def _norm_text(s: str) -> str:
    s = _TS.sub("<T>", s)
    s = _IDS.sub(lambda m: f"{m.group(1)}-<ID>", s)
    s = _FLOAT.sub(lambda m: f"{float(m.group(0)):.4f}", s)  # GPS noise below ~10 m does not change the key
    return " ".join(s.lower().split())


def _first_user_text(messages: list) -> str:
    c = messages[0]["content"] if messages else ""
    if isinstance(c, str):
        return c
    # images (vision calls) are keyed by their prompt only: the demo photos are re-stamped on every download
    return " ".join(b.get("text", "") for b in c if b.get("type") == "text")


def cache_key(agent: str, model: str, system: str, tools: list[dict], messages: list) -> str:
    """Stable across demo runs: agent + prompt + tool set + the NORMALISED case input + which turn of the loop.
    Timestamps, SR/WO numbers and GPS noise are normalised away, so a presenter repeating the recorded story hits
    the cache even when the clock or numbering differ. Tool results are not part of the key: on replay the tools
    still run live (and are logged); only the model's turns come from the recording."""
    turn = sum(1 for m in messages if m.get("role") == "assistant")
    payload = {"agent": agent, "model": model, "system": hashlib.sha256(system.encode()).hexdigest()[:16],
               "tools": sorted(t["name"] for t in tools), "input": _norm_text(_first_user_text(messages)), "turn": turn}
    return hashlib.sha256(_canon(payload).encode()).hexdigest()[:40]


class LLMClient:
    def __init__(self) -> None:
        self._client = None
        self._fallbacks_ok = True
        self._pace_lock = threading.Lock()
        self._last_call = 0.0

    def _pace(self) -> None:
        """Space calls out (free-tier rate limits). Only sleeps when LLM_MIN_INTERVAL_S > 0."""
        gap = settings.llm_min_interval_s
        if gap <= 0:
            return
        with self._pace_lock:
            wait = self._last_call + gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    @staticmethod
    def _retry_after(err: Exception) -> float | None:
        """Seconds to wait if the provider said 'rate limited, retry in N s' (429)."""
        msg = str(err)
        if "429" not in msg and "RESOURCE_EXHAUSTED" not in msg and "rate" not in msg.lower():
            return None
        m = re.search(r"retry in ([0-9.]+)s", msg) or re.search(r"retryDelay'?:\s*'?([0-9.]+)s", msg)
        return float(m.group(1)) if m else 30.0

    @property
    def mode(self) -> str:
        return settings.agent_mode

    def available(self) -> bool:
        if self.mode == "rules":
            return False
        if self.mode == "replay":
            return True
        return bool(settings.provider_key)

    def _sdk(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=1)
        return self._client

    def _path(self, agent: str, key: str) -> Path:
        return Path(settings.agent_cache_dir) / agent / f"{key}.json"

    def create(self, *, agent: str, system: str, tools: list[dict], messages: list, max_tokens: int = 4096,
               timeout_s: float = 30.0) -> LLMResult:
        model = settings.llm_model
        key = cache_key(agent, model, system, tools, messages)
        p = self._path(agent, key)
        if self.mode == "replay":
            if not p.exists():
                raise CacheMiss(f"no recorded response for {agent} turn {key}")
            d = json.loads(p.read_text(encoding="utf-8"))
            return LLMResult(d["content"], d["stop_reason"], d["model"], "replay", d.get("usage"))
        if not self.available():
            raise LLMUnavailable("no API key configured")
        self._pace()
        try:
            res = self._call(model, system, tools, messages, max_tokens, timeout_s)
        except Exception as e:
            # When RECORDING, wait out a rate limit once instead of falling back (a fallback would not be recorded).
            wait = self._retry_after(e) if self.mode == "record" else None
            if wait is None or wait > 70:
                raise
            log.warning("rate limited; waiting %.0f s before retrying (record mode)", wait)
            time.sleep(wait + 1)
            res = self._call(model, system, tools, messages, max_tokens, timeout_s + wait)
        if self.mode == "record":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_canon({"content": res.content, "stop_reason": res.stop_reason, "model": res.model,
                                 "usage": res.usage}), encoding="utf-8")
        return res

    def _call(self, model, system, tools, messages, max_tokens, timeout_s) -> LLMResult:
        if settings.llm_provider == "gemini":
            from app.adapters import gemini

            blocks, stop, model_used, usage = gemini.generate(
                api_key=settings.provider_key, model=model, system=system, tools=tools, messages=messages,
                max_tokens=max_tokens, timeout_s=timeout_s)
            return LLMResult(blocks, stop, model_used, "live", usage)
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
