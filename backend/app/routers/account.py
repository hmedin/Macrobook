"""Account deletion. Removing the auth user cascades to every per-user table (profile, weights, logs, ...)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..auth import current_user_id

router = APIRouter()


class DeleteIn(BaseModel):
    confirm: str


def delete_user_data(c, uid: str) -> None:
    # auth.users is the root: foreign keys with ON DELETE CASCADE remove the user's rows everywhere else,
    # including their sessions. Shared restaurant cache rows (no owner) are public data and stay.
    c.execute("delete from auth.users where id = %s::uuid", (uid,))
    # Parsed cookbooks nobody has a link to any more are removed too (cascades to their recipes).
    c.execute(
        "delete from books b where not exists (select 1 from user_books ub where ub.book_id = b.id)"
    )


@router.delete("/account")
def delete_account(body: DeleteIn, uid: str = Depends(current_user_id)):
    if body.confirm != "DELETE":
        raise HTTPException(422, 'Type "DELETE" to confirm')
    with db.conn() as c:
        delete_user_data(c, uid)
    return {"ok": True}
