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
    query: str = Field(min_length=3, max_length=120)


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


class SaveIn(BaseModel):
    lookup_id: int
    edits: Edits | None = None  # present only if the user changed the numbers


def _food_payload(row: dict) -> dict:
    return {**row, "verified": True, "is_batch": False, "book_servings": None, "user_servings": None,
            "user_total_weight_g": None, "book_title": None, "file_hash": None}


@router.post("/restaurant/save")
def save_lookup(body: SaveIn, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        log = c.execute(
            "select result from lookup_log where id = %s and user_id = %s", (body.lookup_id, uid)
        ).fetchone()
        if not log or not log["result"] or not log["result"].get("found"):
            raise HTTPException(404, "Lookup not found")
        r = log["result"]
        name = r["name"] or "Restaurant item"
        restaurant = r.get("restaurant") or ""

        edited = False
        if body.edits is not None:
            e = body.edits
            edited = (round(e.calories) != round(r["calories"]) or round(e.protein_g) != round(r["protein_g"])
                      or round(e.carbs_g) != round(r["carbs_g"]) or round(e.fat_g) != round(r["fat_g"]))

        if edited:
            # Changed numbers stay private; never poison the shared cache.
            e = body.edits
            row = c.execute(
                f"""insert into foods (owner_id, source_type, restaurant, name, serving_desc, calories, protein_g,
                                      carbs_g, fat_g, is_estimate, estimate_note, source_url, source_quote)
                   values (%s,'custom',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   returning {FOOD_COLS}""",
                (uid, restaurant, f"{name} (edited)", r.get("serving_desc"), e.calories, e.protein_g, e.carbs_g,
                 e.fat_g, bool(r.get("is_estimate")), r.get("notes"), r.get("source_url"), r.get("source_quote")),
            ).fetchone()
            return _food_payload(row)

        row = c.execute(
            f"""insert into foods (owner_id, source_type, restaurant, name, serving_desc, calories, protein_g, carbs_g,
                                  fat_g, is_estimate, estimate_note, source_url, source_quote)
               values (null,'restaurant',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (lower(restaurant), lower(name)) where source_type = 'restaurant'
               do update set name = foods.name
               returning {FOOD_COLS}""",
            (restaurant, name, r.get("serving_desc"), r["calories"], r["protein_g"], r["carbs_g"], r["fat_g"],
             bool(r.get("is_estimate")), r.get("notes"), r.get("source_url"), r.get("source_quote")),
        ).fetchone()
        c.execute("insert into food_verifications (user_id, food_id) values (%s,%s) on conflict do nothing",
                  (uid, row["id"]))
        return _food_payload(row)
