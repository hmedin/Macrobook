"""Load basic foods (USDA FoodData Central, SR Legacy, public domain) into the foods table.

Usage (from backend/, with .env configured and migration 005 applied):
    python scripts/seed_basic_foods.py            # downloads the dataset to a temp folder, then upserts
    python scripts/seed_basic_foods.py <dir>      # use an already-extracted folder of the CSV files

Safe to re-run: rows are upserted by fdc_id. Basic foods are shared and read-only (owner_id is null).
"""
import csv
import io
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.basic_foods import clean_name  # noqa: E402

URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip"
BASE = "FoodData_Central_sr_legacy_food_csv_2018-04/"
FILES = ["food.csv", "food_nutrient.csv", "nutrient.csv", "food_portion.csv", "measure_unit.csv", "food_category.csv"]

# Brand-heavy or overlapping with the restaurant lookup.
EXCLUDE_CATEGORIES = {
    "Baby Foods", "Fast Foods", "Restaurant Foods", "American Indian/Alaska Native Foods",
    "Meals, Entrees, and Side Dishes",
}
NUTRIENTS = {1008: "calories", 1003: "protein_g", 1005: "carbs_g", 1004: "fat_g", 1079: "fiber_g"}
MAX_PORTIONS = 8


def download(dest: Path) -> None:
    with urllib.request.urlopen(URL, timeout=120) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in FILES:  # fixed, known member names only
            (dest / name).write_bytes(z.read(BASE + name))


def _rows(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def _fmt(n: float) -> str:
    return f"{n:g}"


def build_rows(d: Path) -> list[dict]:
    cats = {r["id"]: r["description"] for r in _rows(d / "food_category.csv")}
    units = {r["id"]: r["name"] for r in _rows(d / "measure_unit.csv")}

    foods = {}
    for r in _rows(d / "food.csv"):
        if cats.get(r["food_category_id"]) in EXCLUDE_CATEGORIES:
            continue
        foods[r["fdc_id"]] = {"fdc_id": int(r["fdc_id"]), "name": clean_name(r["description"]), "category": cats.get(r["food_category_id"])}

    wanted = {str(k): v for k, v in NUTRIENTS.items()}
    for r in _rows(d / "food_nutrient.csv"):
        f = foods.get(r["fdc_id"])
        key = wanted.get(r["nutrient_id"])
        if f is not None and key and r["amount"] != "":
            f[key] = float(r["amount"])

    for r in sorted(_rows(d / "food_portion.csv"), key=lambda r: (r["fdc_id"], int(r["seq_num"] or 0))):
        f = foods.get(r["fdc_id"])
        if f is None or not r["gram_weight"]:
            continue
        amount = float(r["amount"] or 1) or 1
        unit = units.get(r["measure_unit_id"], "")
        unit = "" if unit in ("", "undetermined") else unit
        label = " ".join(x for x in [unit, (r["modifier"] or "").strip()] if x) or (r["portion_description"] or "").strip() or "serving"
        grams = float(r["gram_weight"]) / amount  # grams for ONE of this unit
        ports = f.setdefault("portions", [])
        if len(ports) < MAX_PORTIONS and all(p["unit"] != label for p in ports) and grams > 0:
            ports.append({"unit": label, "grams": round(grams, 1)})

    out = []
    for f in foods.values():
        if f.get("calories") is None:
            continue
        out.append({
            "fdc_id": f["fdc_id"], "name": f["name"], "calories": f["calories"],
            "protein_g": f.get("protein_g", 0.0), "carbs_g": f.get("carbs_g", 0.0), "fat_g": f.get("fat_g", 0.0),
            "fiber_g": f.get("fiber_g"), "portions": f.get("portions", []),
        })
    return out


def upsert(conn, rows: list[dict]) -> None:
    from psycopg.types.json import Jsonb

    with conn.cursor() as cur:
        cur.executemany(
            """insert into foods (owner_id, source_type, name, serving_desc, calories, protein_g, carbs_g, fat_g,
                                  fiber_g, fiber_per_100g, portions, fdc_id, is_estimate)
               values (null, 'basic', %s, '100 g', %s, %s, %s, %s, %s, %s, %s, %s, false)
               on conflict (fdc_id) where fdc_id is not null do update set
                 name = excluded.name, calories = excluded.calories, protein_g = excluded.protein_g,
                 carbs_g = excluded.carbs_g, fat_g = excluded.fat_g, fiber_g = excluded.fiber_g,
                 fiber_per_100g = excluded.fiber_per_100g, portions = excluded.portions""",
            [(r["name"], r["calories"], r["protein_g"], r["carbs_g"], r["fat_g"], r["fiber_g"], r["fiber_g"],
              Jsonb(r["portions"]), r["fdc_id"]) for r in rows],
        )


def main() -> None:
    import psycopg

    from app.config import get_settings

    if len(sys.argv) > 1:
        data_dir = Path(sys.argv[1])
    else:
        data_dir = Path(tempfile.mkdtemp(prefix="usda_sr_"))
        print("Downloading USDA SR Legacy...")
        download(data_dir)
    rows = build_rows(data_dir)
    print(f"{len(rows)} basic foods ready")
    with psycopg.connect(get_settings().database_url, prepare_threshold=None) as conn:
        upsert(conn, rows)  # commits when the block exits
    print("Done.")


if __name__ == "__main__":
    main()
