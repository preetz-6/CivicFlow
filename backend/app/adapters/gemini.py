"""Google Gemini provider (optional; LLM_PROVIDER=gemini).

The agent runtime speaks one internal message format (content blocks: text / tool_use / tool_result / image).
This module translates it to Gemini `Content`/`Part`s and back, so agents, the tool loop, the decision log,
fallbacks and record/replay are identical whichever provider is configured.
Raw Gemini parts are kept on each returned block under "_gemini" so thought signatures are sent back unchanged.
"""
from __future__ import annotations

import base64
import json

from google import genai
from google.genai import errors, types

_client: genai.Client | None = None


class GeminiRefusal(Exception):
    pass


def client(api_key: str) -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=api_key)
    return _client


def _parse(s):
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return s


def to_contents(messages: list) -> list[types.Content]:
    names: dict[str, str] = {}
    out: list[types.Content] = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        content = m["content"]
        parts: list[types.Part] = []
        if isinstance(content, str):
            parts.append(types.Part(text=content))
        else:
            for b in content:
                t = b.get("type")
                if "_gemini" in b:  # a part Gemini produced: send it back verbatim (keeps thought_signature)
                    if t == "tool_use":
                        names[b["id"]] = b["name"]
                    parts.append(types.Part.model_validate(b["_gemini"]))
                elif t == "text":
                    parts.append(types.Part(text=b["text"]))
                elif t == "tool_use":
                    names[b["id"]] = b["name"]
                    parts.append(types.Part(function_call=types.FunctionCall(id=b["id"], name=b["name"], args=b.get("input") or {})))
                elif t == "tool_result":
                    data = _parse(b.get("content"))
                    resp = {"error": data} if b.get("is_error") else {"result": data}
                    parts.append(types.Part(function_response=types.FunctionResponse(
                        id=b["tool_use_id"], name=names.get(b["tool_use_id"], "tool"), response=resp)))
                elif t == "image":
                    src = b["source"]
                    parts.append(types.Part.from_bytes(data=base64.b64decode(src["data"]), mime_type=src["media_type"]))
        if parts:
            out.append(types.Content(role=role, parts=parts))
    return out


def to_blocks(resp: types.GenerateContentResponse) -> tuple[list[dict], str]:
    if not resp.candidates:
        raise GeminiRefusal(f"no candidates (prompt feedback: {resp.prompt_feedback})")
    cand = resp.candidates[0]
    blocks: list[dict] = []
    calls = 0
    for i, p in enumerate((cand.content.parts if cand.content else None) or []):
        raw = p.model_dump(mode="json", exclude_none=True)
        if p.function_call is not None:
            calls += 1
            fc = p.function_call
            blocks.append({"type": "tool_use", "id": fc.id or f"gcall-{i}-{fc.name}", "name": fc.name,
                           "input": dict(fc.args or {}), "_gemini": raw})
        elif p.thought:
            blocks.append({"type": "gemini_thought", "_gemini": raw})
        elif p.text is not None:
            blocks.append({"type": "text", "text": p.text, "_gemini": raw})
    fr = cand.finish_reason.name if cand.finish_reason else "STOP"
    if fr in ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY", "RECITATION"):
        return blocks, "refusal"
    if fr == "MAX_TOKENS":
        return blocks, "max_tokens"
    return blocks, "tool_use" if calls else "end_turn"


def generate(*, api_key: str, model: str, system: str, tools: list[dict], messages: list, max_tokens: int,
             timeout_s: float):
    """Returns (blocks, stop_reason, model, usage)."""
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # our loop runs the tools
        http_options=types.HttpOptions(timeout=int(max(timeout_s, 1) * 1000)),
    )
    if tools:
        cfg.tools = [types.Tool(function_declarations=[
            types.FunctionDeclaration(name=t["name"], description=t["description"], parameters_json_schema=t["input_schema"])
            for t in tools])]
    try:
        resp = client(api_key).models.generate_content(model=model, contents=to_contents(messages), config=cfg)
    except errors.APIError:
        raise
    blocks, stop = to_blocks(resp)
    usage = resp.usage_metadata.model_dump(mode="json", exclude_none=True) if resp.usage_metadata else None
    return blocks, stop, resp.model_version or model, usage
