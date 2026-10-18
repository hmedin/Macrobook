"""Ranking for basic-food search. USDA names are messy ("Eggnog" and "Eggplant" also contain "egg"),
so candidates matched by SQL are re-ranked: whole-word matches, plain raw/cooked ingredients, and short
names first; processed products and brand-name entries last."""
from __future__ import annotations

import re

# Cooking-state words describe the food, they aren't part of its name ("rice cooked" is asking for rice).
STATE = {"raw", "cooked", "uncooked", "boiled", "roasted", "fried", "baked", "grilled", "steamed", "dry", "dried", "fresh"}

# Words/phrases that mark processed or prepared products. Penalized, not excluded, so they stay findable.
PROCESSED_WORDS = {
    "breaded", "battered", "nuggets", "patty", "patties", "tenders", "imitation", "substitute", "dehydrated",
    "sliced", "roll", "canned", "babyfood", "formulated", "luncheon", "restaurant", "pickled", "dessert",
}
PROCESSED_PHRASES = ("with added", "dry mix", "ready-to-")
BRAND = re.compile(r"\b[A-Z]{4,}\b")          # e.g. QUAKER, UNCLE BENS
FDP = re.compile(r"\s*\(Includes foods for USDA's Food Distribution Program\)", re.I)


def clean_name(name: str) -> str:
    return FDP.sub("", name).strip()


def tokens(q: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9']+", q.lower()) if t]


def _variants(t: str) -> set[str]:
    out = {t, t + "s", t + "es"}
    if t.endswith("s"):
        out.add(t[:-1])
    if t.endswith("es"):
        out.add(t[:-2])
    return out


def score(name: str, toks: list[str]) -> float:
    low = name.lower()
    words = set(re.findall(r"[a-z0-9']+", low))
    first = low.split(",")[0].strip()
    first_words = set(re.findall(r"[a-z0-9']+", first))
    food = [t for t in toks if t not in STATE] or toks
    s = 0.0

    for t in toks:
        v = _variants(t)
        if words & v:
            s += 10
        elif t in low:
            s += 2                       # only inside another word (egg -> eggplant)
    if all(words & _variants(t) for t in toks):
        s += 15                          # every word that was typed appears as a whole word
    for t in food:
        if first_words & _variants(t):
            s += 8
    if all(first_words & _variants(t) for t in food):
        s += 12                          # the food itself is what was asked for
    # The entry whose name IS the query ("Egg, whole, raw" for "egg", "Rice, white, ..." for "rice cooked").
    if len(food) == 1 and first in _variants(food[0]):
        s += 25
    elif len(food) > 1 and first == " ".join(food):
        s += 25

    if ", raw" in low or ", cooked" in low:
        s += 6
    if "meat only" in low:
        s += 15
    asked = set(toks)  # a processed word the user typed ("canned tuna") isn't held against the result
    s -= 35 * len((words & PROCESSED_WORDS) - asked)
    s -= 35 * sum(1 for p in PROCESSED_PHRASES if p in low and p not in " ".join(toks))
    if BRAND.search(name):
        s -= 15
    return s - 0.05 * len(name)


# For the staples people search for most, the standard entries go first. Matched by name prefix
# (case-insensitive); a prefix that matches nothing is ignored.
_EGG = ["Egg, whole, raw, fresh", "Egg, whole, cooked, hard-boiled", "Egg, whole, cooked, scrambled",
        "Egg, whole, cooked, fried", "Egg, white, raw, fresh", "Egg, yolk, raw, fresh"]
_MILK = ["Milk, whole, 3.25% milkfat, with added vitamin D",
         "Milk, reduced fat, fluid, 2% milkfat, with added vitamin A and vitamin D",
         "Milk, lowfat, fluid, 1% milkfat, with added vitamin A and vitamin D",
         "Milk, nonfat, fluid, with added vitamin A and vitamin D (fat free or skim)"]
_BACON = ["Pork, cured, bacon, pre-sliced, cooked, pan-fried", "Pork, cured, bacon, cooked, baked",
          "Pork, cured, bacon, cooked, microwaved", "Pork, cured, bacon, unprepared"]
_CHICKEN = ["Chicken, broiler or fryers, breast, skinless, boneless, meat only, raw",
            "Chicken, broilers or fryers, breast, meat only, cooked, roasted",
            "Chicken, broilers or fryers, breast, meat only, raw"]
_WHITE_RICE = ["Rice, white, long-grain, regular, enriched, cooked", "Rice, white, long-grain, regular, raw, enriched"]
_BROWN_RICE = ["Rice, brown, long-grain, cooked", "Rice, brown, long-grain, raw"]
_OATS = ["Oats", "Cereals, oats, regular and quick, not fortified, dry",
         "Cereals, oats, regular and quick, unenriched, cooked with water (includes boiling and microwaving), without salt"]
_BREAD = ["Bread, white, commercially prepared (includes soft bread crumbs)", "Bread, whole-wheat, commercially prepared"]
_PASTA = ["Pasta, cooked, enriched, without added salt", "Pasta, whole-wheat, cooked", "Pasta, dry, enriched"]
_BEEF = ["Beef, ground, 85% lean meat / 15% fat, raw", "Beef, ground, 93% lean meat / 7% fat, raw",
         "Beef, ground, 80% lean meat / 20% fat, raw", "Beef, ground, 95% lean meat / 5% fat, raw"]
_SALMON = ["Fish, salmon, Atlantic, farmed, raw", "Fish, salmon, Atlantic, farmed, cooked, dry heat"]
_TUNA = ["Fish, tuna, light, canned in water, drained solids", "Fish, tuna, light, canned in water, without salt, drained solids"]
_POTATO = ["Potatoes, flesh and skin, raw", "Potatoes, baked, flesh and skin, without salt"]

PINNED: dict[str, list[str]] = {
    "egg": _EGG, "eggs": _EGG, "milk": _MILK, "bacon": _BACON, "chicken breast": _CHICKEN,
    "rice": _WHITE_RICE + _BROWN_RICE, "white rice": _WHITE_RICE, "brown rice": _BROWN_RICE,
    "rice cooked": _WHITE_RICE[:1] + _BROWN_RICE[:1], "cooked rice": _WHITE_RICE[:1] + _BROWN_RICE[:1],
    "white rice cooked": _WHITE_RICE[:1], "cooked white rice": _WHITE_RICE[:1],
    "brown rice cooked": _BROWN_RICE[:1], "cooked brown rice": _BROWN_RICE[:1],
    "oats": _OATS, "oatmeal": _OATS, "bread": _BREAD, "pasta": _PASTA, "spaghetti": _PASTA,
    "ground beef": _BEEF, "salmon": _SALMON, "tuna": _TUNA, "canned tuna": _TUNA,
    "potato": _POTATO, "potatoes": _POTATO,
}


def rank(rows: list[dict], q: str, limit: int = 12) -> list[dict]:
    toks = tokens(q)
    ordered = sorted(rows, key=lambda r: score(r["name"], toks), reverse=True)
    pinned: list[dict] = []
    for prefix in PINNED.get(" ".join(toks), []):
        hit = next((r for r in ordered if r["name"].lower().startswith(prefix.lower()) and r not in pinned), None)
        if hit is not None:
            pinned.append(hit)
    return (pinned + [r for r in ordered if r not in pinned])[:limit]
