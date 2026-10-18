"""Per-portion macros for recipes that are stored per-serving or as a whole batch."""
from __future__ import annotations

KEYS = ("calories", "protein_g", "carbs_g", "fat_g")


def per_portion(
    macros: dict[str, float],
    is_batch: bool,
    book_servings: float | None,
    user_servings: float | None,
) -> dict[str, float] | None:
    """Macros for ONE portion given how many portions the user splits the recipe into.

    - Batch recipe: macros are the whole batch, so a split is required (None if missing).
    - Per-serving recipe: macros are per the book's "makes N"; a different split rescales
      (total = per * N_book, portion = total / N_user).
    """
    if is_batch:
        if not user_servings:
            return None
        return {k: macros[k] / user_servings for k in KEYS}
    if book_servings and user_servings and user_servings != book_servings:
        scale = book_servings / user_servings
        return {k: macros[k] * scale for k in KEYS}
    return dict(macros)
