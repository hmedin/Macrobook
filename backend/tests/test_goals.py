from datetime import date, timedelta

import pytest

from app.services import goals


def test_bmr_known_values():
    # 80kg, 180cm, 30y male: 800 + 1125 - 150 + 5 = 1780
    assert goals.bmr_mifflin("male", 80, 180, 30) == 1780
    # 60kg, 165cm, 30y female: 600 + 1031.25 - 150 - 161 = 1320.25
    assert goals.bmr_mifflin("female", 60, 165, 30) == pytest.approx(1320.25)


def test_tdee_multiplier():
    assert goals.tdee("male", 80, 180, 30, "sedentary") == pytest.approx(1780 * 1.2)


def test_age_from_birthdate():
    assert goals.age_from_birthdate(date(1990, 6, 15), date(2026, 6, 14)) == 35
    assert goals.age_from_birthdate(date(1990, 6, 15), date(2026, 6, 15)) == 36


def test_target_loss_rate():
    rate = goals.lb_per_week_to_kg(-0.5)
    t = goals.calorie_target(2500, rate, "male")
    assert not t.floor_applied
    assert t.calories == pytest.approx(2250, abs=10)


def test_target_floor_applied():
    t = goals.calorie_target(1700, goals.lb_per_week_to_kg(-2), "female")
    assert t.floor_applied and t.calories == 1200


def test_exercise_kcal():
    # 3 mi (4.83 km) run at 67 kg ~ 323 kcal
    assert goals.exercise_kcal("run", 67, None, 4.83) == pytest.approx(323, abs=2)
    assert goals.exercise_kcal("cycle", 70, 60, None) == 350
    assert goals.exercise_kcal("run", 70, None, None) is None


def test_macros_sum_close_to_calories():
    m = goals.macro_targets(2000, 80)
    total = m["protein_g"] * 4 + m["carbs_g"] * 4 + m["fat_g"] * 9
    assert abs(total - 2000) < 30


def test_smoothing_dampens_noise():
    start = date(2026, 1, 1)
    data = [(start + timedelta(days=i), 80 + (1 if i % 2 else -1)) for i in range(10)]
    trend = goals.smooth_weights(data)
    assert max(w for _, w in trend) - min(w for _, w in trend) < 1.0


def _series(days, start_w, end_w):
    start = date(2026, 1, 1)
    pts = [(start + timedelta(days=i), start_w + (end_w - start_w) * i / (days - 1)) for i in range(0, days, 2)]
    return start, pts


def test_adaptive_not_eligible_early():
    start, pts = _series(10, 80, 79.5)
    res = goals.adaptive_maintenance(pts, {}, set())
    assert not res.eligible and res.reasons


def test_adaptive_measured_maintenance():
    start, pts = _series(29, 80, 79.0)  # lost 1kg over 28 days
    days = [start + timedelta(days=i) for i in range(29)]
    intake = {d: 2000.0 for d in days}
    res = goals.adaptive_maintenance(pts, intake, set(days))
    assert res.eligible
    # span is 28 days; deficit = 7700/28 = 275 -> maintenance ~2275
    assert res.measured_maintenance == pytest.approx(2275, abs=5)


def test_adaptive_needs_complete_days():
    start, pts = _series(29, 80, 79.0)
    days = [start + timedelta(days=i) for i in range(29)]
    intake = {d: 2000.0 for d in days}
    res = goals.adaptive_maintenance(pts, intake, set(days[:5]))
    assert not res.eligible


def test_adaptive_progress_counts():
    start, pts = _series(29, 80, 79.0)
    days = [start + timedelta(days=i) for i in range(29)]
    intake = {d: 2000.0 for d in days}
    res = goals.adaptive_maintenance(pts, intake, set(days[:5]))
    assert res.progress["complete_days"] == 5 and res.progress["complete_needed"] == 14
    assert res.progress["weighins"] == len(pts)
