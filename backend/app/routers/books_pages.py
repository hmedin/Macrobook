"""Which pages of a book hold recipes, so the browser can save small page images for the side-by-side checks."""
from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..auth import current_user_id

router = APIRouter()


@router.get("/books/{book_id}/pages")
def book_pages(book_id: int, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        if not c.execute(
            "select 1 from user_books where user_id = %s and book_id = %s", (uid, book_id)
        ).fetchone():
            raise HTTPException(404, "Book not found")
        rows = c.execute(
            "select distinct source_page from foods where book_id = %s and source_page is not null order by 1",
            (book_id,),
        ).fetchall()
    return {"pages": [r["source_page"] for r in rows]}
