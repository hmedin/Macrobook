"""Cookbook import. The PDF is processed from a temp file and deleted; only facts are stored."""
import hashlib
import logging
import os
import tempfile
import threading
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from psycopg.types.json import Jsonb

from .. import db
from ..auth import current_user_id
from ..config import get_settings
from ..services.ai_extract import extract_with_ai
from ..services.recipe_parser import parse_pdf_pages

router = APIRouter()
log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_BOOKS_PER_USER = 25
MIN_UPDATE_OVERLAP = 0.3  # share of recipe names that must match for a file to count as a new edition
_import_slots = threading.BoundedSemaphore(2)


def read_texts(path: str) -> list[str]:
    with pymupdf.open(path) as doc:
        return [p.get_text() for p in doc]


def candidate_pages(texts: list[str], parsed_pages: set[int]) -> list[int]:
    """Pages the local parser skipped that still look like recipes (worth a cheap AI read)."""
    out = []
    for i, t in enumerate(texts):
        low = t.lower()
        if i in parsed_pages or len(t.strip()) < 200:
            continue
        if "ingredient" in low or ("calor" in low and "protein" in low):
            out.append(i)
    return out


def build_rows(texts: list[str]) -> tuple[list[dict], dict]:
    """Local parser first (free, exact); Claude only for the pages it couldn't read."""
    local, _missed = parse_pdf_pages(texts)
    rows = [
        {"name": r.name, "serving_desc": r.serving_desc, "calories": r.calories, "protein_g": r.protein_g,
         "carbs_g": r.carbs_g, "fat_g": r.fat_g, "page": r.page, "is_batch": r.serving_desc == "1 entire batch",
         "book_servings": r.servings, "is_estimate": False, "estimate_note": None, "ingredients": None,
         "consistent": r.consistent, "source": "local"}
        for r in local
    ]
    info = {"local": len(rows), "ai_read": 0, "estimated": 0, "ai_error": None, "ai_pages": 0}

    pages = candidate_pages(texts, {r["page"] for r in rows})
    if pages and get_settings().anthropic_api_key:
        info["ai_pages"] = len(pages)
        try:
            for r in extract_with_ai(texts, pages):
                if any(x["page"] == r.page and x["name"].lower() == r.name.lower() for x in rows):
                    continue
                rows.append({
                    "name": r.name, "serving_desc": r.serving_desc, "calories": r.calories,
                    "protein_g": r.protein_g, "carbs_g": r.carbs_g, "fat_g": r.fat_g, "page": r.page,
                    "is_batch": r.is_batch, "book_servings": r.book_servings, "is_estimate": r.is_estimate,
                    "estimate_note": r.estimate_note, "ingredients": r.ingredients or None,
                    "consistent": r.consistent, "source": "ai",
                })
                info["estimated" if r.is_estimate else "ai_read"] += 1
        except Exception as exc:  # keep whatever the local parser found
            log.warning("AI extraction failed: %s", exc)
            info["ai_error"] = "Some pages couldn't be read automatically."
    rows.sort(key=lambda r: r["page"])
    return rows, info


def _migrate(c, uid: str, old_id: int, new_id: int) -> dict:
    """Move a user from an old edition to a new one, carrying over what is still valid."""
    if old_id == new_id:
        return {"same_file": True}
    key = lambda r: r["name"].strip().lower()
    old = {key(r): r for r in c.execute(
        "select id, name, calories, protein_g, carbs_g, fat_g from foods where book_id = %s", (old_id,)).fetchall()}
    new = {key(r): r for r in c.execute(
        "select id, name, calories, protein_g, carbs_g, fat_g from foods where book_id = %s", (new_id,)).fetchall()}
    # An "update" that shares almost no recipes is a different book: keep both, change nothing.
    overlap = len([k for k in old if k in new]) / max(1, min(len(old), len(new)))
    if overlap < MIN_UPDATE_OVERLAP:
        return {"same_file": False, "skipped": True, "overlap_pct": round(overlap * 100)}
    same = lambda a, b: all(round(float(a[k])) == round(float(b[k])) for k in ("calories", "protein_g", "carbs_g", "fat_g"))

    changed, kept_verified = [], 0
    for k, o in old.items():
        n = new.get(k)
        if not n:
            continue
        # Splits and total weights are about how the user cooks, so they carry over regardless.
        c.execute(
            """insert into food_prefs (user_id, food_id, servings, total_weight_g)
               select user_id, %s, servings, total_weight_g from food_prefs where user_id = %s and food_id = %s
               on conflict do nothing""",
            (n["id"], uid, o["id"]),
        )
        if same(o, n):
            r = c.execute(
                """insert into food_verifications (user_id, food_id)
                   select user_id, %s from food_verifications where user_id = %s and food_id = %s
                   on conflict do nothing returning 1""",
                (n["id"], uid, o["id"]),
            ).fetchone()
            kept_verified += 1 if r else 0
        else:
            changed.append(n["name"])

    c.execute("delete from user_books where user_id = %s and book_id = %s", (uid, old_id))
    left = c.execute("select count(*) as n from user_books where book_id = %s", (old_id,)).fetchone()["n"]
    if left == 0:
        c.execute("delete from books where id = %s", (old_id,))
    return {
        "same_file": False,
        "changed": changed[:30], "changed_count": len(changed),
        "added_count": len([k for k in new if k not in old]),
        "removed_count": len([k for k in old if k not in new]),
        "kept_verified": kept_verified,
    }


@router.post("/books/import")
def import_book(
    file: UploadFile = File(...),
    title: str = Form(""),
    replaces: int | None = Form(None),  # id of the user's older edition to replace
    uid: str = Depends(current_user_id),
):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(422, "Please upload a PDF")

    with db.conn() as c:
        n = c.execute("select count(*) as n from user_books where user_id = %s", (uid,)).fetchone()["n"]
        if replaces is not None and not c.execute(
            "select 1 from user_books where user_id = %s and book_id = %s", (uid, replaces)
        ).fetchone():
            raise HTTPException(404, "The book to update wasn't found")
    if n >= MAX_BOOKS_PER_USER and replaces is None:
        raise HTTPException(429, "Book limit reached")

    # Stream to a temp file while hashing; deleted in `finally`.
    h = hashlib.sha256()
    size = 0
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "PDF is too large (100 MB max)")
                h.update(chunk)
                out.write(chunk)
        file_hash = h.hexdigest()
        name = title.strip() or Path(file.filename).stem.replace("_", " ")

        with db.conn() as c:
            book = c.execute("select id, status, title from books where file_hash = %s", (file_hash,)).fetchone()
            if book and book["status"] == "ready":
                # Someone already parsed this exact file; reuse the facts for the user who proves they have it.
                c.execute("insert into user_books (user_id, book_id) values (%s,%s) on conflict do nothing",
                          (uid, book["id"]))
                cnt = c.execute("select count(*) as n from foods where book_id = %s", (book["id"],)).fetchone()["n"]
                swap = _migrate(c, uid, replaces, book["id"]) if replaces is not None else None
                return {"id": book["id"], "title": book["title"], "file_hash": file_hash,
                        "recipes": cnt, "reused": True, "needs_review_pages": [], "replaced": swap}

        # Keep memory bounded on small hosts: at most two PDFs are read at once.
        if not _import_slots.acquire(timeout=60):
            raise HTTPException(503, "The server is busy importing other cookbooks. Please try again in a minute.")
        try:
            try:
                texts = read_texts(tmp)
            except Exception as exc:
                raise HTTPException(422, "Could not read that PDF") from exc
            rows, info = build_rows(texts)
        finally:
            _import_slots.release()
        if not rows:
            raise HTTPException(422, "No recipes were found in this PDF")

        with db.conn() as c:
            row = c.execute(
                """insert into books (title, file_hash, status) values (%s,%s,'ready')
                   on conflict (file_hash) do update set status = 'ready'
                   returning id""",
                (name, file_hash),
            ).fetchone()
            book_id = row["id"]
            c.execute("delete from foods where book_id = %s", (book_id,))
            with c.cursor() as cur:
                cur.executemany(
                    """insert into foods (owner_id, source_type, book_id, name, serving_desc, calories,
                                          protein_g, carbs_g, fat_g, source_page, is_batch, book_servings,
                                          is_estimate, estimate_note, ingredients)
                       values (null,'recipe',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [(book_id, r["name"], r["serving_desc"], r["calories"], r["protein_g"], r["carbs_g"],
                      r["fat_g"], r["page"], r["is_batch"], r["book_servings"], r["is_estimate"],
                      r["estimate_note"], Jsonb(r["ingredients"]) if r["ingredients"] else None)
                     for r in rows],
                )
            c.execute("insert into user_books (user_id, book_id) values (%s,%s) on conflict do nothing",
                      (uid, book_id))
            swap = _migrate(c, uid, replaces, book_id) if replaces is not None else None
        return {
            "id": book_id, "title": name, "file_hash": file_hash, "recipes": len(rows), "reused": False,
            "pages": len(texts), "read_by_ai": info["ai_read"], "estimated": info["estimated"],
            "ai_error": info["ai_error"], "replaced": swap, "flagged": [r["name"] for r in rows if not r["consistent"]],
        }
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@router.get("/books")
def list_books(uid: str = Depends(current_user_id)):
    with db.conn() as c:
        return c.execute(
            """select b.id, b.title, b.file_hash, count(f.id) as recipes
               from user_books ub
               join books b on b.id = ub.book_id
               left join foods f on f.book_id = b.id
               where ub.user_id = %s
               group by b.id order by b.title""",
            (uid,),
        ).fetchall()


@router.delete("/books/{book_id}")
def remove_book(book_id: int, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        c.execute("delete from user_books where user_id = %s and book_id = %s", (uid, book_id))
        left = c.execute("select count(*) as n from user_books where book_id = %s", (book_id,)).fetchone()["n"]
        if left == 0:
            c.execute("delete from books where id = %s", (book_id,))  # cascades to its foods
    return {"ok": True}


@router.post("/foods/{food_id}/verify")
def verify_food(food_id: int, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        ok = c.execute(
            """select 1 from foods f where f.id = %(fid)s and
               (f.owner_id = %(uid)s or f.source_type = 'restaurant'
                or exists (select 1 from user_books ub where ub.book_id = f.book_id and ub.user_id = %(uid)s))""",
            {"fid": food_id, "uid": uid},
        ).fetchone()
        if not ok:
            raise HTTPException(404, "Food not found")
        c.execute(
            "insert into food_verifications (user_id, food_id) values (%s,%s) on conflict do nothing",
            (uid, food_id),
        )
    return {"ok": True}
