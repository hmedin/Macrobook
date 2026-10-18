"""Deterministic recipe-page parser for cookbooks that print a per-serving macro block.

Returns facts only (name, serving info, macros, page). Pages that don't match are left for
the Claude-based fallback. Only macros/names are kept; directions and prose are discarded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NUM = r"(\d[\d,]*(?:\.\d+)?)"
# Anchored to whole lines so ingredient text like "1/3-fat cream cheese" can't match.
RE_CAL = re.compile(r"^\s*" + NUM + r"\s*(?:k?cal(?:ories)?)\s*$", re.I | re.M)
RE_PRO = re.compile(r"^\s*" + NUM + r"\s*g?\*?\s*protein\s*$", re.I | re.M)
RE_CARB = re.compile(r"^\s*" + NUM + r"\s*g?\*?\s*(?:net\s*)?carbs?(?:ohydrates?)?\s*$", re.I | re.M)
RE_FAT = re.compile(r"^\s*" + NUM + r"\s*g?\*?\s*fat\s*$", re.I | re.M)
RE_SERVES = re.compile(r"(?:makes|serves|yields?)\s*(\d+)", re.I)
RE_PER = re.compile(r"per\s+(serving|bowl|portion|cup|slice|piece|burger|sandwich|taco|wrap)", re.I)


@dataclass
class ParsedRecipe:
    page: int  # 0-based
    name: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    servings: int | None
    serving_desc: str
    consistent: bool  # calories roughly match 4P + 4C + 9F; False means review before trusting


def _f(m: re.Match) -> float:
    return float(m.group(1).replace(",", ""))


def _title(lines: list[str]) -> str:
    parts: list[str] = []
    for ln in lines[:4]:
        ln = ln.strip()
        if not ln or ln.endswith(":") or re.match(r"^[\d½¼¾⅓⅔]", ln) or ln.lower() in ("ingredients", "instructions"):
            break
        if parts and not (ln.isupper() or ln.istitle()):
            break
        parts.append(ln)
    return " ".join(parts).strip()


def _title_after_macros(text: str, fat: re.Match) -> str:
    """Some layouts print the title just after the macros block instead of at the top."""
    for ln in text[fat.end():].splitlines():
        ln = ln.strip()
        if not ln or ln.lower().startswith(("per ", "back to")) or ln.endswith(":") or re.match(r"^[\d½¼¾⅓⅔]", ln):
            continue
        return ln if len(ln) <= 80 else ""
    return ""


def _clean_name(name: str) -> str:
    return " ".join(w if w[0].isupper() and not w.isupper() else w.capitalize() for w in name.split())


def parse_page(text: str, page: int) -> ParsedRecipe | None:
    cal, pro, carb, fat = (r.search(text) for r in (RE_CAL, RE_PRO, RE_CARB, RE_FAT))
    if not (cal and pro and carb and fat):
        return None
    lines = [l for l in text.splitlines() if l.strip()]
    name = _title(lines) or _title_after_macros(text, fat)
    if not name:
        return None
    sv = RE_SERVES.search(text)
    per = RE_PER.search(text)
    unit = per.group(1).lower() if per else "serving"
    n = int(sv.group(1)) if sv else None
    if re.search(r"per\s+entire\s+(?:batch|recipe)", text, re.I):
        unit, n = "entire batch", None
    c, p, cb, f = _f(cal), _f(pro), _f(carb), _f(fat)
    implied = 4 * p + 4 * cb + 9 * f
    return ParsedRecipe(
        page=page, name=_clean_name(name),
        calories=c, protein_g=p, carbs_g=cb, fat_g=f,
        servings=n, serving_desc=f"1 {unit}" + (f" (recipe makes {n})" if n else ""),
        consistent=c > 0 and abs(implied - c) / c <= 0.25,
    )


def parse_pdf_pages(texts: list[str]) -> tuple[list[ParsedRecipe], list[int]]:
    """Returns (parsed recipes, indices of pages that did not parse)."""
    ok: list[ParsedRecipe] = []
    missed: list[int] = []
    for i, t in enumerate(texts):
        r = parse_page(t, i)
        if r:
            ok.append(r)
        else:
            missed.append(i)
    return ok, missed
