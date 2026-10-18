"""Goal calculations: BMR/TDEE, calorie targets, macro split, weight trend, adaptive maintenance."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

KCAL_PER_KG = 7700.0
LB_PER_KG = 2.20462

# Activity reflects daily life only; workouts are logged separately.
ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "high": 1.725,
    "extreme": 1.9,
}

CALORIE_FLOOR = {"female": 1200, "male": 1500}

# Adaptive eligibility thresholds
MIN_DAYS_SPAN = 21
MIN_COMPLETE_DAYS = 14
MIN_WEIGHINS = 4


def age_from_birthdate(birthdate: date, today: date) -> int:
    years = today.year - birthdate.year
    if (today.month, today.day) < (birthdate.month, birthdate.day):
        years -= 1
    return years


def bmr_mifflin(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sex == "male" else base - 161


def tdee(sex: str, weight_kg: float, height_cm: float, age: int, activity: str) -> float:
    return bmr_mifflin(sex, weight_kg, height_cm, age) * ACTIVITY_MULTIPLIERS[activity]


# Net (above resting) MET values for time-based activities.
NET_MET = {"cycle": 5.0, "swim": 5.0, "strength": 3.0, "hiit": 7.0, "other": 4.0}
EAT_BACK = {"none": 0.0, "half": 0.5, "all": 1.0}


def exercise_kcal(kind: str, weight_kg: float, duration_min: float | None, distance_km: float | None) -> float | None:
    """Estimate net calories burned. Returns None if there isn't enough info."""
    if kind == "run" and distance_km:
        return round(1.0 * weight_kg * distance_km)  # ~1 kcal/kg/km net
    if kind == "walk" and distance_km:
        return round(0.5 * weight_kg * distance_km)
    if kind in ("run", "walk") and duration_min:
        met = 8.0 if kind == "run" else 2.5
        return round(met * weight_kg * duration_min / 60)
    if duration_min:
        return round(NET_MET.get(kind, NET_MET["other"]) * weight_kg * duration_min / 60)
    return None


def lb_per_week_to_kg(rate_lb: float) -> float:
    return rate_lb / LB_PER_KG


@dataclass
class Target:
    calories: int
    floor_applied: bool
    daily_adjustment: int  # signed kcal vs maintenance actually applied


def calorie_target(maintenance: float, rate_kg_per_week: float, sex: str) -> Target:
    """rate_kg_per_week is negative for loss, positive for gain."""
    adjustment = rate_kg_per_week * KCAL_PER_KG / 7
    raw = maintenance + adjustment
    floor = CALORIE_FLOOR[sex]
    if raw < floor:
        return Target(floor, True, round(floor - maintenance))
    return Target(round(raw), False, round(adjustment))


def macro_targets(calories: int, weight_kg: float, protein_g_per_kg: float = 1.8, fat_pct: float = 0.28) -> dict:
    protein = round(protein_g_per_kg * weight_kg)
    fat = round(calories * fat_pct / 9)
    carbs = max(0, round((calories - protein * 4 - fat * 9) / 4))
    return {"protein_g": protein, "carbs_g": carbs, "fat_g": fat}


def smooth_weights(weights: list[tuple[date, float]], alpha: float = 0.1) -> list[tuple[date, float]]:
    """Exponentially smoothed trend, one point per weigh-in, ordered by date."""
    out: list[tuple[date, float]] = []
    trend: float | None = None
    for d, w in sorted(weights):
        trend = w if trend is None else trend + alpha * (w - trend)
        out.append((d, trend))
    return out


@dataclass
class AdaptiveResult:
    eligible: bool
    reasons: list[str]
    measured_maintenance: float | None = None
    progress: dict | None = None


def adaptive_maintenance(
    trend: list[tuple[date, float]],
    daily_intake: dict[date, float],
    complete_days: set[date],
) -> AdaptiveResult:
    """Measured maintenance = avg intake - (change in trend weight * 7700 / days).

    Only uses days marked complete. Not eligible until enough data exists.
    """
    span = (trend[-1][0] - trend[0][0]).days if len(trend) >= 2 else 0
    used = [d for d in complete_days if d in daily_intake and trend and trend[0][0] <= d <= trend[-1][0]]
    progress = {
        "weighins": len(trend), "weighins_needed": MIN_WEIGHINS,
        "span_days": span, "span_needed": MIN_DAYS_SPAN,
        "complete_days": len(used), "complete_needed": MIN_COMPLETE_DAYS,
    }
    reasons: list[str] = []
    if len(trend) < MIN_WEIGHINS:
        reasons.append(f"Need at least {MIN_WEIGHINS} weigh-ins ({len(trend)} so far).")
    if span < MIN_DAYS_SPAN:
        reasons.append(f"Need at least {MIN_DAYS_SPAN} days of tracking ({span} so far).")
    if len(used) < MIN_COMPLETE_DAYS:
        reasons.append(f"Need at least {MIN_COMPLETE_DAYS} fully logged days ({len(used)} so far).")
    if reasons:
        return AdaptiveResult(False, reasons, None, progress)

    avg_intake = sum(daily_intake[d] for d in used) / len(used)
    delta_kg = trend[-1][1] - trend[0][1]
    measured = avg_intake - delta_kg * KCAL_PER_KG / span
    return AdaptiveResult(True, [], round(measured), progress)
