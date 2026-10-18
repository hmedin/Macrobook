from app.services.basic_foods import clean_name, rank


def top(q, names, n=1):
    return [r["name"] for r in rank([{"name": x} for x in names], q, n)]


def test_whole_word_beats_substring():
    names = ["Eggnog", "Eggplant, raw", "Egg, whole, raw, fresh", "Egg, yolk, dried"]
    assert top("egg", names)[0] == "Egg, whole, raw, fresh"


def test_plain_ingredient_beats_processed_and_brand():
    names = [
        "Chicken breast, roll, oven-roasted",
        "Chicken breast tenders, breaded, uncooked",
        "Chicken, broilers or fryers, breast, meat only, cooked, roasted",
    ]
    assert top("chicken breast", names)[0].startswith("Chicken, broilers or fryers, breast, meat only")
    rice = ["Rice noodles, cooked", "Rice, brown, parboiled, cooked, UNCLE BENS", "Rice, white, long-grain, regular, cooked"]
    assert top("rice cooked", rice)[0] == "Rice, white, long-grain, regular, cooked"


def test_clean_name_strips_program_note():
    assert clean_name("Oats (Includes foods for USDA's Food Distribution Program)") == "Oats"


def test_typed_processing_word_is_not_penalized():
    names = ["Tuna, fresh, bluefin, raw", "Fish, tuna, light, canned in water, drained solids"]
    assert top("canned tuna", names)[0].startswith("Fish, tuna, light, canned")


def test_pinned_staples_come_first_and_missing_pins_are_ignored():
    names = ["Egg, yolk, raw, fresh", "Egg, white, raw, fresh", "Egg, whole, raw, fresh", "Eggplant, raw"]
    assert top("egg", names, 3) == ["Egg, whole, raw, fresh", "Egg, white, raw, fresh", "Egg, yolk, raw, fresh"]
    assert top("milk", ["Milk, sheep, fluid"], 1) == ["Milk, sheep, fluid"]   # no pinned entry present -> unchanged
