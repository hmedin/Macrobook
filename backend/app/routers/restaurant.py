"""Restaurant lookup. Shared-cache saves are bound to what Claude actually returned for that user's lookup."""
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from .. import db
from ..auth import current_user_id
from ..services import lookup as lookup_service

router = APIRouter()

DAILY_LOOKUP_LIMIT = 30

FOOD_COLS = """id, name, source_type, restaurant, serving_desc, calories, protein_g, carbs_g, fat_g,
               is_estimate, source_url, source_quote, estimate_note"""


class LookupIn(BaseModel):
    query: str = Field(min_length=3, max_length=160)


@router.post("/restaurant/lookup")
def do_lookup(body: LookupIn, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        n = c.execute(
            "select count(*) as n from lookup_log where user_id = %s and created_at > now() - interval '1 day'",
            (uid,),
        ).fetchone()["n"]
    if n >= DAILY_LOOKUP_LIMIT:
        raise HTTPException(429, "Daily lookup limit reached. Try again tomorrow, or add the food manually.")
    try:
        result = lookup_service.lookup(body.query.strip())
    except lookup_service.LookupError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:  # network / API errors
        raise HTTPException(502, "Lookup failed. Please try again.") from exc

    with db.conn() as c:
        row = c.execute(
            "insert into lookup_log (user_id, query, result) values (%s,%s,%s) returning id",
            (uid, body.query.strip(), Jsonb(result)),
        ).fetchone()
    return {"lookup_id": row["id"], **result}


class Edits(BaseModel):
    calories: float = Field(ge=0, le=6000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=800)
    fat_g: float = Field(ge=0, le=500)


class Pick(BaseModel):
    index: int = Field(ge=0, le=20)
    edits: Edits | None = None  # present only if the user changed the numbers


class SaveIn(BaseModel):
    lookup_id: int
    picks: list[Pick] = Field(min_length=1, max_length=lookup_service.MAX_ITEMS)


def _food_payload(row: dict) -> dict:
    return {**row, "verified": True, "is_batch": False, "book_servings": None, "user_servings": None,
            "user_total_weight_g": None, "book_title": None, "file_hash": None}


def _notes(item: dict) -> str | None:
    parts = [item.get("notes") or ""]
    if item.get("assumptions"):
        parts.append("Assumed: " + "; ".join(item["assumptions"]))
    return " ".join(p for p in parts if p).strip() or None


def _save_one(c, uid: str, item: dict, edits: Edits | None) -> dict:
    name = item["name"] or "Restaurant item"
    restaurant = item.get("restaurant") or ""
    edited = edits is not None and (
        round(edits.calories) != round(item["calories"]) or round(edits.protein_g) != round(item["protein_g"])
        or round(edits.carbs_g) != round(item["carbs_g"]) or round(edits.fat_g) != round(item["fat_g"])
    )
    note = _notes(item)

    if edited:
        # Changed numbers stay private; never poison the shared cache.
        row = c.execute(
            f"""insert into foods (owner_id, source_type, restaurant, name, serving_desc, calories, protein_g,
                                  carbs_g, fat_g, is_estimate, estimate_note, source_url, source_quote)
               values (%s,'custom',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               returning {FOOD_COLS}""",
            (uid, restaurant, f"{name} (edited)", item.get("serving_desc"), edits.calories, edits.protein_g,
             edits.carbs_g, edits.fat_g, bool(item.get("is_estimate")), note, item.get("source_url"),
             item.get("source_quote")),
        ).fetchone()
        return _food_payload(row)

    row = c.execute(
        f"""insert into foods (owner_id, source_type, restaurant, name, serving_desc, calories, protein_g, carbs_g,
                              fat_g, is_estimate, estimate_note, source_url, source_quote)
           values (null,'restaurant',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (lower(restaurant), lower(name)) where source_type = 'restaurant'
           do update set name = foods.name
           returning {FOOD_COLS}""",
        (restaurant, name, item.get("serving_desc"), item["calories"], item["protein_g"], item["carbs_g"],
         item["fat_g"], bool(item.get("is_estimate")), note, item.get("source_url"), item.get("source_quote")),
    ).fetchone()
    c.execute("insert into food_verifications (user_id, food_id) values (%s,%s) on conflict do nothing",
              (uid, row["id"]))
    return _food_payload(row)


@router.post("/restaurant/save")
def save_lookup(body: SaveIn, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        log = c.execute(
            "select result from lookup_log where id = %s and user_id = %s", (body.lookup_id, uid)
        ).fetchone()
        result = (log or {}).get("result") or {}
        items = result.get("items") or []
        if not result.get("found") or not items:
            raise HTTPException(404, "Lookup not found")
        foods = []
        for pick in body.picks:
            if pick.index >= len(items):
                raise HTTPException(422, "Unknown item")
            foods.append(_save_one(c, uid, items[pick.index], pick.edits))
    return {"foods": foods}
