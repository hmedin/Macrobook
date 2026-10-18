"""Restaurant nutrition lookup: Claude + web search, validated and flagged before anything is trusted."""
from __future__ import annotations

import json
import os
import re
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from ..config import get_settings

LOOKUP_MODEL = os.environ.get("LOOKUP_MODEL", "claude-haiku-5-5")
MAX_CONTINUES = 3

SYSTEM = """You find nutrition facts for a single restaurant menu item using web search.

Rules:
- Prefer the restaurant's own official nutrition page, PDF, or menu. Use a third-party site only if no official source is found, and say so.
- Report numbers for ONE standard serving of the item exactly as the source lists it. Do not add or subtract sides, sauces, or sizes unless the item name asks for them.
- Copy numbers from the page. Never invent, average, or guess. If you cannot find reliable numbers, set found to false.
- Keep serving_desc short (for example "1 sandwich" or "medium, 4 oz") and notes to one or two sentences. Mention in notes if other sources disagree.
- "source_quote" must be the exact text from the page that contains the calories (and macros if shown), so a person can check it.
- confidence: "official" (restaurant's own site/PDF), "third_party" (another site's copy of the data), or "estimate" (you had to estimate any value).
- Answer with ONLY a JSON object, no prose, no code fences, with exactly these keys:
  found (bool), restaurant (string), name (string), serving_desc (string), calories (number),
  protein_g (number), carbs_g (number), fat_g (number), source_url (string), source_quote (string),
  confidence ("official"|"third_party"|"estimate"), notes (string)."""


class LookupResult(BaseModel):
    found: bool
    restaurant: str = ""
    name: str = ""
    serving_desc: str = ""
    calories: float = Field(default=0, ge=0, le=6000)
    protein_g: float = Field(default=0, ge=0, le=500)
    carbs_g: float = Field(default=0, ge=0, le=800)
    fat_g: float = Field(default=0, ge=0, le=500)
    source_url: str = ""
    source_quote: str = ""
    confidence: Literal["official", "third_party", "estimate"] = "estimate"
    notes: str = ""


class LookupError(Exception):
    pass


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LookupError("The model did not return a result")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LookupError("The model returned malformed data") from exc


def _final_text(content) -> str:
    return "".join(b.text for b in content if getattr(b, "type", "") == "text")


def validate(r: LookupResult) -> dict:
    """Adds sanity flags. The numbers still go through the user's side-by-side check."""
    out = r.model_dump()
    implied = 4 * r.protein_g + 4 * r.carbs_g + 9 * r.fat_g
    has_macros = (r.protein_g + r.carbs_g + r.fat_g) > 0
    out["consistent"] = (not has_macros) or (r.calories > 0 and abs(implied - r.calories) / r.calories <= 0.30)
    out["has_macros"] = has_macros
    quote = r.source_quote.lower()
    # The quoted line should actually contain the calorie figure we report.
    out["quote_matches"] = bool(r.source_quote) and str(int(round(r.calories))) in re.sub(r"[,\s]", "", quote)
    if r.confidence == "estimate":
        out["is_estimate"] = True
    else:
        out["is_estimate"] = False
    return out


def lookup(query: str) -> dict:
    key = get_settings().anthropic_api_key
    if not key:
        raise LookupError("Restaurant lookup isn't configured (missing API key)")
    client = anthropic.Anthropic(api_key=key)

    messages: list[dict] = [{"role": "user", "content": f"Find the nutrition facts for: {query}"}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}]

    response = None
    for _ in range(MAX_CONTINUES + 1):
        response = client.messages.create(
            model=LOOKUP_MODEL,
            max_tokens=2500,
            system=SYSTEM,
            tools=tools,
            output_config={"effort": "low"},
            messages=messages,
        )
        if response.stop_reason == "pause_turn":
            messages = messages[:1] + [{"role": "assistant", "content": response.content}]
            continue
        break
    if response is None or response.stop_reason == "refusal":
        raise LookupError("The lookup was declined")
    if response.stop_reason == "max_tokens":
        raise LookupError("The lookup ran too long; try a more specific name")

    try:
        result = LookupResult.model_validate(_extract_json(_final_text(response.content)))
    except ValidationError as exc:
        raise LookupError("The result didn't look right") from exc
    if not result.found or result.calories <= 0:
        return {"found": False}
    return validate(result)
