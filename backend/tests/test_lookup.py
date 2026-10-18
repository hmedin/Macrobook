from app.services.lookup import Item, LookupResult, _extract_json, validate_item


def test_extract_json_ignores_surrounding_text():
    assert _extract_json('Sure! {"found": false} Done.') == {"found": False}


def test_validate_flags_inconsistent_and_quote():
    ok = Item(name="x", calories=420, protein_g=29, carbs_g=41, fat_g=16,
              source_quote="Calories 420 Total Fat 16g", confidence="official")
    v = validate_item(ok)
    assert v["consistent"] and v["quote_matches"] and not v["is_estimate"]

    bad = Item(name="x", calories=900, protein_g=29, carbs_g=41, fat_g=16,
               source_quote="Calories 420", confidence="estimate")
    v = validate_item(bad)
    assert not v["consistent"] and not v["quote_matches"] and v["is_estimate"]


def test_multi_item_result_with_assumptions_and_other_values():
    r = LookupResult.model_validate({
        "found": True, "meal_note": "",
        "items": [
            {"name": "Grilled Teriyaki Chicken", "calories": 275, "protein_g": 33, "carbs_g": 14, "fat_g": 10,
             "confidence": "third_party", "assumptions": ["standard entree portion"],
             "other_values": [{"calories": 300, "source": "fastfoodnutrition.org"}]},
            {"name": "Chow Mein", "calories": 510, "protein_g": 13, "carbs_g": 80, "fat_g": 20, "confidence": "official"},
        ],
    })
    assert len(r.items) == 2
    assert r.items[0].assumptions == ["standard entree portion"] and r.items[0].other_values[0].calories == 300
