import pytest

from app.services.servings import per_portion

M = {"calories": 600.0, "protein_g": 45.0, "carbs_g": 58.0, "fat_g": 20.0}


def test_per_serving_default_unchanged():
    assert per_portion(M, False, 10, None) == M
    assert per_portion(M, False, 10, 10) == M


def test_per_serving_resplit():
    # makes 10 at 600 kcal = 6000 total; split into 8 -> 750 each
    r = per_portion(M, False, 10, 8)
    assert r["calories"] == pytest.approx(750)
    assert r["protein_g"] == pytest.approx(56.25)


def test_batch_requires_split():
    batch = {"calories": 3600.0, "protein_g": 432.0, "carbs_g": 103.0, "fat_g": 171.0}
    assert per_portion(batch, True, None, None) is None
    assert per_portion(batch, True, None, 12)["calories"] == pytest.approx(300)
    assert per_portion(batch, True, None, 1)["calories"] == 3600


def test_no_book_servings_ignores_split():
    assert per_portion(M, False, None, 4) == M
