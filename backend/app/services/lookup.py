"""Restaurant nutrition lookup: Claude + web search, validated and flagged before anything is trusted.

A request can be one item or a whole order (a plate, a burger and fries). Each item comes back with the
assumptions made for vague details and the other figures seen when sources disagree.
"""
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
MAX_ITEMS = 6

SYSTEM = """You find nutrition facts for restaurant menu items using web search.

The request may be one item or a whole order (for example a plate with a side and an entree, or a burger and fries). Split it into the distinct menu items a person would log separately, and return one entry per item, each for ONE standard serving.

Rules:
- Prefer the restaurant's own official nutrition page, PDF, or menu. Use a third-party site only if no official source is found, and say so.
- When the request leaves details open (size, crust, flavor, toppings, sauce), assume the restaurant's most common default and list each assumption briefly in "assumptions". Put the size or variant you chose in the item name, for example "Pepperoni Pizza, Large Hand Tossed". Set found to false only if you cannot tell which restaurant or what food is meant.
- For items sold in pieces (pizza slices, wings, nuggets), report ONE piece unless the request names a count. For combos, use the restaurant's own definition of what the combo contains, and return each component separately.
- Copy numbers from the page. Never invent, average, or guess them. If you cannot find reliable numbers for an item, leave it out and mention that in meal_note.
- When sources disagree, report the official figure if there is one; otherwise report the figure that MOST sources agree on for the restaurant's standard portion (not an outlier), and list up to three other calorie figures you saw in "other_values", each with a short source name.
- "source_quote" must be the exact text from the page that contains the calories (and macros if shown), so a person can check it.
- confidence: "official" (restaurant's own site or PDF), "third_party" (another site's copy of the data), or "estimate" (you had to estimate any value).
- Keep serving_desc short (for example "1 slice (1/8 of 14 in)" or "1 entree, 6 oz") and notes to one or two sentences.
- Answer with ONLY a JSON object, no prose, no code fences:
  {"found": bool, "meal_note": string,
   "items": [{"name": string, "restaurant": string, "serving_desc": string, "calories": number,
              "protein_g": number, "carbs_g": number, "fat_g": number, "source_url": string,
              "source_quote": string, "confidence": "official"|"third_party"|"estimate", "notes": string,
              "assumptions": [string], "other_values": [{"calories": number, "source": string}]}]}"""


class OtherValue(BaseModel):
    calories: float = Field(default=0, ge=0, le=10000)
    source: str = ""


class Item(BaseModel):
    name: str = ""
    restaurant: str = ""
    serving_desc: str = ""
    calories: float = Field(default=0, ge=0, le=6000)
    protein_g: float = Field(default=0, ge=0, le=500)
    carbs_g: float = Field(default=0, ge=0, le=800)
    fat_g: float = Field(default=0, ge=0, le=500)
    source_url: str = ""
    source_quote: str = ""
    confidence: Literal["official", "third_party", "estimate"] = "estimate"
    notes: str = ""
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    other_values: list[OtherValue] = Field(default_factory=list, max_length=5)


class LookupResult(BaseModel):
    found: bool
    meal_note: str = ""
    items: list[Item] = Field(default_factory=list, max_length=MAX_ITEMS)


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


def validate_item(r: Item) -> dict:
    """Adds sanity flags. The numbers still go through the user's side-by-side check."""
    out = r.model_dump()
    implied = 4 * r.protein_g + 4 * r.carbs_g + 9 * r.fat_g
    has_macros = (r.protein_g + r.carbs_g + r.fat_g) > 0
    out["consistent"] = (not has_macros) or (r.calories > 0 and abs(implied - r.calories) / r.calories <= 0.30)
    out["has_macros"] = has_macros
    # The quoted line should actually contain the calorie figure we report.
    out["quote_matches"] = bool(r.source_quote) and str(int(round(r.calories))) in re.sub(r"[,\s]", "", r.source_quote.lower())
    out["is_estimate"] = r.confidence == "estimate"
    return out


def lookup(query: str) -> dict:
    key = get_settings().anthropic_api_key
    if not key:
        raise LookupError("Restaurant lookup isn't configured (missing API key)")
    client = anthropic.Anthropic(api_key=key)

    messages: list[dict] = [{"role": "user", "content": f"Find the nutrition facts for: {query}"}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}]

    response = None
    for _ in range(MAX_CONTINUES + 1):
        response = client.messages.create(
            model=LOOKUP_MODEL,
            max_tokens=4000,
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
        raise LookupError("The lookup ran too long; try asking for fewer items at once")

    try:
        result = LookupResult.model_validate(_extract_json(_final_text(response.content)))
    except ValidationError as exc:
        raise LookupError("The result didn't look right") from exc
    items = [validate_item(i) for i in result.items if i.name and i.calories > 0]
    if not result.found or not items:
        return {"found": False, "meal_note": result.meal_note}
    return {"found": True, "meal_note": result.meal_note, "items": items}
