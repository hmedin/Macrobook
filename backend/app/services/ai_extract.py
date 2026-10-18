"""Claude fallback for cookbook pages the local parser can't read. Sends page TEXT only (cheap), never images.

Stage 1 extracts recipes (macros only if printed). Stage 2 estimates macros from ingredient amounts for
recipes with none printed; those are flagged as estimates everywhere.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import anthropic

from ..config import get_settings

EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL", "claude-haiku-5-5")
ESTIMATE_MODEL = os.environ.get("ESTIMATE_MODEL", "claude-haiku-5-5")
PAGES_PER_CALL = 6
MAX_AI_PAGES = 200
WORKERS = 6

NUM_OR_NULL = {"anyOf": [{"type": "number"}, {"type": "null"}]}
INT_OR_NULL = {"anyOf": [{"type": "integer"}, {"type": "null"}]}

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "recipes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer"},
                    "name": {"type": "string"},
                    "macros_printed": {"type": "boolean"},
                    "basis": {"type": "string", "enum": ["serving", "batch", "unknown"]},
                    "calories": NUM_OR_NULL,
                    "protein_g": NUM_OR_NULL,
                    "carbs_g": NUM_OR_NULL,
                    "fat_g": NUM_OR_NULL,
                    "servings": INT_OR_NULL,
                    "ingredients": {"type": "array", "items": {"type": "string"}},
                    "note": {"type": "string"},
                },
                "required": ["page", "name", "macros_printed", "basis", "calories", "protein_g", "carbs_g",
                             "fat_g", "servings", "ingredients", "note"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["recipes"],
    "additionalProperties": False,
}

EXTRACT_SYSTEM = """You extract recipe facts from cookbook page text. Pages are separated by lines like "=== PAGE 12 ===".

For each recipe on these pages return:
- page: the PAGE number where the recipe's title or ingredients appear
- name: the recipe title, properly capitalized
- macros_printed: true ONLY if the book prints calories/protein/carbs/fat for this recipe. Never compute or guess them.
- basis: what the printed macros refer to: "serving" (per serving/portion), "batch" (whole recipe/batch), or "unknown"
- calories, protein_g, carbs_g, fat_g: the printed numbers, or null when not printed
- servings: how many servings the recipe makes/serves if stated, else null
- ingredients: ONLY when macros_printed is false, list every ingredient exactly as written with its amount. Otherwise an empty list.
- note: normally an empty string. If the book prints a RANGE for any value (for example "450-500 calories"), use the midpoint and say so here, quoting the printed range. Also note anything else a reader should double-check.

Skip pages that are not recipes (introductions, techniques, tables of contents, shopping guides). A recipe needs a name and either printed macros or at least three ingredients."""

ESTIMATE_SCHEMA = {
    "type": "object",
    "properties": {
        "estimates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "calories": {"type": "number"},
                    "protein_g": {"type": "number"},
                    "carbs_g": {"type": "number"},
                    "fat_g": {"type": "number"},
                    "assumptions": {"type": "string"},
                },
                "required": ["index", "calories", "protein_g", "carbs_g", "fat_g", "assumptions"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["estimates"],
    "additionalProperties": False,
}

ESTIMATE_SYSTEM = """You estimate nutrition for home recipes from their ingredient lists.

For each recipe, estimate the TOTAL calories, protein_g, carbs_g and fat_g of the WHOLE recipe (all servings together), using typical average nutrition values for each ingredient and amount (raw weights unless stated otherwise). Count cooking oil and butter only if listed. Treat "to taste" and garnish amounts as negligible. Briefly state any key assumptions in one sentence."""


@dataclass
class AIRecipe:
    page: int  # 0-based
    name: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    is_batch: bool
    book_servings: int | None
    serving_desc: str
    is_estimate: bool = False
    estimate_note: str | None = None
    ingredients: list[str] = field(default_factory=list)
    consistent: bool = True


def _client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    if not key:
        raise RuntimeError("missing API key")
    return anthropic.Anthropic(api_key=key)


def _call(client, model: str, system: str, user: str, schema: dict, max_tokens: int) -> dict:
    r = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
    )
    if r.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"extraction stopped: {r.stop_reason}")
    text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    return json.loads(text)


def _extract_chunk(client, texts: list[str], pages: list[int]) -> list[dict]:
    body = "\n\n".join(f"=== PAGE {p + 1} ===\n{texts[p]}" for p in pages)
    return _call(client, EXTRACT_MODEL, EXTRACT_SYSTEM, body, EXTRACT_SCHEMA, 8000)["recipes"]


def _consistent(c: float, p: float, cb: float, f: float) -> bool:
    return c > 0 and abs(4 * p + 4 * cb + 9 * f - c) / c <= 0.25


def extract_with_ai(texts: list[str], pages: list[int]) -> list[AIRecipe]:
    """`pages` are 0-based indices of pages the local parser couldn't read."""
    pages = pages[:MAX_AI_PAGES]
    if not pages:
        return []
    client = _client()
    chunks = [pages[i : i + PAGES_PER_CALL] for i in range(0, len(pages), PAGES_PER_CALL)]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        raw = [r for part in pool.map(lambda ch: _extract_chunk(client, texts, ch), chunks) for r in part]

    out: list[AIRecipe] = []
    needs_estimate: list[dict] = []
    for r in raw:
        name = (r.get("name") or "").strip()
        page = int(r["page"]) - 1
        if not name or page < 0 or page >= len(texts):
            continue
        n = r.get("servings") if (r.get("servings") or 0) > 0 else None
        if r["macros_printed"] and all(r[k] is not None for k in ("calories", "protein_g", "carbs_g", "fat_g")):
            c, p, cb, f = (float(r[k]) for k in ("calories", "protein_g", "carbs_g", "fat_g"))
            batch = r["basis"] == "batch"
            parts = [r["note"].strip()] if (r.get("note") or "").strip() else []
            if r["basis"] == "unknown":
                parts.append("Serving basis wasn't clear in the book; check the page.")
            note = " ".join(parts) or None
            out.append(AIRecipe(
                page=page, name=name, calories=c, protein_g=p, carbs_g=cb, fat_g=f, is_batch=batch,
                book_servings=None if batch else n,
                serving_desc="1 entire batch" if batch else f"1 serving" + (f" (recipe makes {n})" if n else ""),
                estimate_note=note, consistent=_consistent(c, p, cb, f),
            ))
        elif len(r["ingredients"]) >= 3:
            needs_estimate.append({**r, "name": name, "page": page, "servings": n})

    if needs_estimate:
        out.extend(_estimate(client, needs_estimate))
    out.sort(key=lambda x: x.page)
    return out


def _estimate(client, items: list[dict]) -> list[AIRecipe]:
    results: list[AIRecipe] = []
    for start in range(0, len(items), 8):
        batch = items[start : start + 8]
        user = "\n\n".join(
            f"Recipe {i}: {it['name']}\nIngredients:\n" + "\n".join(f"- {x}" for x in it["ingredients"])
            for i, it in enumerate(batch)
        )
        try:
            est = _call(client, ESTIMATE_MODEL, ESTIMATE_SYSTEM, user, ESTIMATE_SCHEMA, 4000)["estimates"]
        except Exception:
            continue
        by_idx = {e["index"]: e for e in est}
        for i, it in enumerate(batch):
            e = by_idx.get(i)
            if not e or e["calories"] <= 0:
                continue
            n = it["servings"]
            div = n or 1
            note = "Estimated from the ingredient list, not printed in the book. " + (e["assumptions"] or "")
            results.append(AIRecipe(
                page=it["page"], name=it["name"],
                calories=e["calories"] / div, protein_g=e["protein_g"] / div,
                carbs_g=e["carbs_g"] / div, fat_g=e["fat_g"] / div,
                is_batch=n is None, book_servings=n,
                serving_desc=f"1 serving (recipe makes {n})" if n else "1 entire batch",
                is_estimate=True, estimate_note=note.strip(), ingredients=it["ingredients"],
                consistent=_consistent(e["calories"], e["protein_g"], e["carbs_g"], e["fat_g"]),
            ))
    return results
