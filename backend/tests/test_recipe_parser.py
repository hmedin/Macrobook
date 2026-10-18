from app.services.recipe_parser import parse_page

PAGE = """Test Mac n’ Cheese
Meat & Sauce Base:
900g ground beef
150g (1 ½ cups) cheddar
100g (½ cup) 1/3-fat cream cheese
ingredients
instructions
Cook everything. Divide into 10 servings.
58G Carbs
600 Calories
45g Protein
 20G Fat
Per Serving: makes 10
back to table of contents 41
"""


def test_parses_macros_block_and_ignores_ingredient_text():
    r = parse_page(PAGE, 40)
    assert r is not None
    assert r.name == "Test Mac N’ Cheese"
    assert (r.calories, r.protein_g, r.carbs_g, r.fat_g) == (600, 45, 58, 20)
    assert r.servings == 10
    assert r.consistent


def test_entire_batch_is_labeled():
    text = PAGE.replace("Per Serving: makes 10", "PER ENTIRE BATCH")
    r = parse_page(text, 1)
    assert r.serving_desc == "1 entire batch" and r.servings is None


def test_inconsistent_macros_flagged():
    r = parse_page(PAGE.replace("600 Calories", "1200 Calories"), 1)
    assert not r.consistent


def test_non_recipe_page_returns_none():
    assert parse_page("WHO IS STEALTH HEALTH?\nHey, my name is...", 1) is None


def test_title_after_macros_and_asterisk_values():
    text = ("Chicken:\n900g chicken\nDivide into 10 portions.\n4.\n81g* Carbs\n595 Calories\n41g Protein\n 11G Fat\n"
            "PER ENTIRE BATCH\nGreen Soup Bowls\nToppings:\n1 bunch cilantro\nback to table of contents 25")
    r = parse_page(text, 24)
    assert r and r.name == "Green Soup Bowls" and r.carbs_g == 81 and r.calories == 595
