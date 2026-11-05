"""Vision helpers (analyze_photo for Agent 1, vision_compare for Agent 4). Same record/replay cache as agents."""
from __future__ import annotations

import base64
import io

from PIL import Image

from app.adapters.llm import LLMUnavailable, llm, text_of
from app.adapters.storage import storage
from app.agents.runtime.loop import extract_json
from app.agents.runtime.tools import props, tool
from app.models import Attachment

MAX_SIDE = 1024


def image_block(att: Attachment) -> dict:
    data = storage.read(att.path)
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def ask_vision(name: str, images: list[Attachment], prompt: str) -> dict:
    if not llm.available():
        return {"skipped": True, "reason": "vision model not configured (rules mode)"}
    content = [image_block(a) for a in images] + [{"type": "text", "text": prompt}]
    try:
        res = llm.create(agent=name, system="You inspect civic-infrastructure photos for a municipal corporation. "
                                            "Answer with ONLY a JSON object.",
                         tools=[], messages=[{"role": "user", "content": content}], max_tokens=1500, timeout_s=25)
        if res.stop_reason == "refusal":
            return {"skipped": True, "reason": "model declined"}
        return extract_json(text_of(res.content))
    except LLMUnavailable as e:
        return {"skipped": True, "reason": str(e)}
    except Exception as e:
        return {"skipped": True, "reason": f"vision call failed: {type(e).__name__}"}


@tool("analyze_photo",
      "Look at a citizen's photo: what civic issue does it show, does it match the chosen category, how severe? "
      "Returns {shows, matches_category, suggested_category, severity, notes} or {skipped}.",
      {"properties": props(attachment_id="integer", claimed_category="string"), "required": ["attachment_id"]})
def analyze_photo(ctx, attachment_id: int, claimed_category: str | None = None):
    att = ctx.db.get(Attachment, attachment_id)
    if att is None:
        return {"error": f"no attachment {attachment_id}"}
    return ask_vision("vision_analyze", [att], (
        f"The citizen filed this photo under category '{claimed_category}'. Categories: POTHOLE, DAMAGED_ROAD, "
        "STREETLIGHT, GARBAGE, WATER_LEAK, DRAIN_BLOCKED, WATERLOGGING, OPEN_MANHOLE, TREE_FALL, OTHER. "
        'Reply {"shows": "<short description>", "matches_category": true|false, "suggested_category": "<one of the list>", '
        '"severity": "LOW|MEDIUM|HIGH|DANGEROUS", "notes": "<one sentence>"}'))
