from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db
from ..auth import current_user_id
from ..services import goals, servings as portions

router = APIRouter()


# ---------- Profile & goals ----------

class ProfileIn(BaseModel):
    sex: Literal["male", "female"]
    birthdate: date
    height_cm: float = Field(gt=50, lt=260)
    activity_level: Literal["sedentary", "light", "moderate", "high", "extreme"]
    unit_pref: Literal["imperial", "metric"] = "imperial"
    goal_rate_kg_per_week: float = Field(ge=-1.5, le=1.0)
    exercise_eat_back: Literal["none", "half", "all"] = "none"


@router.get("/profile")
def get_profile(uid: str = Depends(current_user_id)):
    with db.conn() as c:
        row = c.execute("select * from profiles where user_id = %s", (uid,)).fetchone()
    return row


@router.put("/profile")
def put_profile(p: ProfileIn, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        c.execute(
            """insert into profiles (user_id, sex, birthdate, height_cm, activity_level, unit_pref,
                                     goal_rate_kg_per_week, exercise_eat_back)
               values (%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (user_id) do update set sex=excluded.sex, birthdate=excluded.birthdate,
                 height_cm=excluded.height_cm, activity_level=excluded.activity_level,
                 unit_pref=excluded.unit_pref, goal_rate_kg_per_week=excluded.goal_rate_kg_per_week,
                 exercise_eat_back=excluded.exercise_eat_back""",
            (uid, p.sex, p.birthdate, p.height_cm, p.activity_level, p.unit_pref,
             p.goal_rate_kg_per_week, p.exercise_eat_back),
        )
    return {"ok": True}


class WeightIn(BaseModel):
    date: date
    weight_kg: float = Field(gt=20, lt=400)


@router.get("/weights")
def list_weights(uid: str = Depends(current_user_id)):
    with db.conn() as c:
        rows = c.execute(
            "select date, weight_kg from weights where user_id = %s order by date", (uid,)
        ).fetchall()
    trend = goals.smooth_weights([(r["date"], float(r["weight_kg"])) for r in rows])
    return [
        {"date": r["date"], "weight_kg": float(r["weight_kg"]), "trend_kg": round(t[1], 2)}
        for r, t in zip(rows, trend)
    ]


@router.put("/weights")
def put_weight(w: WeightIn, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        c.execute(
            """insert into weights (user_id, date, weight_kg) values (%s,%s,%s)
               on conflict (user_id, date) do update set weight_kg = excluded.weight_kg""",
            (uid, w.date, w.weight_kg),
        )
    return {"ok": True}


ADAPTIVE_WARNING = (
    "This is calculated from everything you've logged. If any food went unlogged, the number will be "
    "too low and your targets inaccurate."
)


def _adaptive_inputs(uid: str):
    with db.conn() as c:
        prof = c.execute("select * from profiles where user_id = %s", (uid,)).fetchone()
        wts = c.execute(
            "select date, weight_kg from weights where user_id = %s order by date", (uid,)
        ).fetchall()
        intake = c.execute(
            "select date, sum(calories) as kcal from food_logs where user_id = %s group by date", (uid,)
        ).fetchall()
        done = c.execute("select date from complete_days where user_id = %s", (uid,)).fetchall()
    trend = goals.smooth_weights([(r["date"], float(r["weight_kg"])) for r in wts])
    res = goals.adaptive_maintenance(
        trend, {r["date"]: float(r["kcal"]) for r in intake}, {r["date"] for r in done}
    )
    return prof, trend, res


def _load_goal(uid: str, today: date) -> dict:
    prof, trend, res = _adaptive_inputs(uid)
    if not prof or not trend:
        raise HTTPException(409, "Complete your profile and log a weight first")
    weight = trend[-1][1]
    age = goals.age_from_birthdate(prof["birthdate"], today)
    formula = goals.tdee(prof["sex"], weight, float(prof["height_cm"]), age, prof["activity_level"])

    method, maintenance, withdrawn = "formula", formula, False
    if prof["goal_mode"] == "adaptive" and not prof["adaptive_opt_out"]:
        if res.eligible and res.measured_maintenance:
            method, maintenance = "adaptive", float(res.measured_maintenance)
        else:
            withdrawn = True  # data no longer qualifies; quietly use the formula and say so

    target = goals.calorie_target(maintenance, float(prof["goal_rate_kg_per_week"]), prof["sex"])
    return {
        "method": method,
        "adaptive_withdrawn": withdrawn,
        "maintenance": round(maintenance),
        "formula_maintenance": round(formula),
        "calories": target.calories,
        "floor_applied": target.floor_applied,
        "trend_weight_kg": round(weight, 1),
        **goals.macro_targets(target.calories, weight),
    }


@router.get("/goal")
def get_goal(uid: str = Depends(current_user_id)):
    return _load_goal(uid, date.today())


@router.get("/goal/adaptive")
def adaptive_status(uid: str = Depends(current_user_id)):
    prof, trend, res = _adaptive_inputs(uid)
    if not prof:
        raise HTTPException(409, "Complete your profile first")
    return {
        "eligible": res.eligible,
        "reasons": res.reasons,
        "progress": res.progress,
        "measured_maintenance": res.measured_maintenance,
        "mode": prof["goal_mode"],
        "opt_out": prof["adaptive_opt_out"],
        "warning": ADAPTIVE_WARNING,
    }


class ModeIn(BaseModel):
    mode: Literal["tdee", "adaptive"] | None = None
    opt_out: bool | None = None  # True = never offer adaptive; False = allow it to be offered again


@router.put("/goal/mode")
def set_goal_mode(b: ModeIn, uid: str = Depends(current_user_id)):
    prof, _trend, res = _adaptive_inputs(uid)
    if not prof:
        raise HTTPException(409, "Complete your profile first")
    mode = b.mode or prof["goal_mode"]
    opt_out = prof["adaptive_opt_out"] if b.opt_out is None else b.opt_out
    if opt_out:
        mode = "tdee"  # locked to the formula
    if mode == "adaptive" and not res.eligible:
        raise HTTPException(409, "Adaptive goals unlock after more logged data: " + " ".join(res.reasons))
    with db.conn() as c:
        c.execute(
            "update profiles set goal_mode = %s, adaptive_opt_out = %s where user_id = %s", (mode, opt_out, uid)
        )
    return {"mode": mode, "opt_out": opt_out}


# ---------- Exercise ----------

class ExerciseIn(BaseModel):
    date: date
    type: Literal["run", "walk", "cycle", "swim", "strength", "hiit", "other"]
    duration_min: float | None = Field(default=None, gt=0, le=1440)
    distance_km: float | None = Field(default=None, gt=0, le=500)
    kcal_burned: float | None = Field(default=None, gt=0, le=10000)  # overrides the estimate


@router.post("/exercise")
def add_exercise(e: ExerciseIn, uid: str = Depends(current_user_id)):
    kcal = e.kcal_burned
    if kcal is None:
        with db.conn() as c:
            w = c.execute(
                "select weight_kg from weights where user_id = %s order by date desc limit 1", (uid,)
            ).fetchone()
        if not w:
            raise HTTPException(409, "Log a weight first so calories can be estimated")
        kcal = goals.exercise_kcal(e.type, float(w["weight_kg"]), e.duration_min, e.distance_km)
        if kcal is None:
            raise HTTPException(422, "Provide distance, duration, or calories burned")
    with db.conn() as c:
        row = c.execute(
            """insert into exercise_logs (user_id, date, type, duration_min, distance_km, kcal_burned)
               values (%s,%s,%s,%s,%s,%s) returning id""",
            (uid, e.date, e.type, e.duration_min, e.distance_km, kcal),
        ).fetchone()
    return {"id": row["id"], "kcal_burned": kcal}


@router.delete("/exercise/{ex_id}")
def delete_exercise(ex_id: int, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        c.execute("delete from exercise_logs where id = %s and user_id = %s", (ex_id, uid))
    return {"ok": True}


# ---------- Foods ----------

class FoodIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    serving_desc: str | None = None
    calories: float = Field(ge=0, le=10000)
    protein_g: float = Field(default=0, ge=0, le=1000)
    carbs_g: float = Field(default=0, ge=0, le=1000)
    fat_g: float = Field(default=0, ge=0, le=1000)
    is_batch: bool = False
    book_servings: float | None = Field(default=None, gt=0, le=200)


@router.post("/foods")
def create_food(f: FoodIn, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        row = c.execute(
            """insert into foods (owner_id, source_type, name, serving_desc, calories, protein_g, carbs_g, fat_g,
                                  is_batch, book_servings)
               values (%s,'custom',%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
            (uid, f.name, f.serving_desc, f.calories, f.protein_g, f.carbs_g, f.fat_g, f.is_batch, f.book_servings),
        ).fetchone()
    return {"id": row["id"]}


@router.get("/foods/search")
def search_foods(q: str, uid: str = Depends(current_user_id)):
    """Unified autocomplete across the user's custom foods, their books, and the restaurant cache."""
    q = q.strip()
    if len(q) < 2:
        return []
    with db.conn() as c:
        rows = c.execute(
            """select f.id, f.name, f.source_type, f.restaurant, b.title as book_title, f.serving_desc,
                      f.calories, f.protein_g, f.carbs_g, f.fat_g, f.is_estimate, f.source_url, f.source_quote, f.estimate_note, f.source_page, f.book_id, b.file_hash,
                      f.is_batch, f.book_servings, fp.servings as user_servings, fp.total_weight_g as user_total_weight_g,
                      (v.user_id is not null) as verified
               from foods f
               left join books b on b.id = f.book_id
               left join food_verifications v on v.food_id = f.id and v.user_id = %(uid)s
               left join food_prefs fp on fp.food_id = f.id and fp.user_id = %(uid)s
               where f.name ilike %(like)s
                 and (f.owner_id = %(uid)s
                      or f.source_type = 'restaurant'
                      or exists (select 1 from user_books ub where ub.book_id = f.book_id and ub.user_id = %(uid)s))
               order by (f.owner_id = %(uid)s) desc, length(f.name)
               limit 25""",
            {"uid": uid, "like": f"%{q}%"},
        ).fetchall()
    return rows


# ---------- Logging ----------

class LogIn(BaseModel):
    date: date
    meal_slot: Literal["breakfast", "lunch", "dinner", "snack"] = "snack"
    food_id: int | None = None
    servings: float = Field(default=1, gt=0, le=50)  # number of portions eaten
    split: float | None = Field(default=None, gt=0, le=200)  # portions the recipe is divided into (this log only)
    # For one-off entries with no saved food:
    name: str | None = None
    calories: float | None = None
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0


@router.post("/logs")
def add_log(l: LogIn, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        if l.food_id is not None:
            f = c.execute(
                """select f.* from foods f where f.id = %(fid)s and
                   (f.owner_id = %(uid)s or f.source_type = 'restaurant'
                    or exists (select 1 from user_books ub where ub.book_id = f.book_id and ub.user_id = %(uid)s))""",
                {"fid": l.food_id, "uid": uid},
            ).fetchone()
            if not f:
                raise HTTPException(404, "Food not found")
            pref = c.execute(
                "select servings from food_prefs where user_id = %s and food_id = %s", (uid, l.food_id)
            ).fetchone()
            n_user = l.split or (float(pref["servings"]) if pref and pref["servings"] else None)
            port = portions.per_portion(
                {k: float(f[k]) for k in portions.KEYS}, bool(f["is_batch"]),
                float(f["book_servings"]) if f["book_servings"] else None, n_user,
            )
            if port is None:
                raise HTTPException(409, "This recipe is a whole batch. Say how many servings it makes.")
            name, cal = f["name"], port["calories"]
            p, cb, ft, est = port["protein_g"], port["carbs_g"], port["fat_g"], f["is_estimate"]
        else:
            if not l.name or l.calories is None:
                raise HTTPException(422, "Provide food_id, or name and calories")
            name, cal, p, cb, ft, est = l.name, l.calories, l.protein_g, l.carbs_g, l.fat_g, False
        row = c.execute(
            """insert into food_logs (user_id, date, meal_slot, food_id, name, servings, calories,
                                      protein_g, carbs_g, fat_g, is_estimate)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
            (uid, l.date, l.meal_slot, l.food_id, name, l.servings, cal * l.servings,
             p * l.servings, cb * l.servings, ft * l.servings, est),
        ).fetchone()
    return {"id": row["id"]}


class SplitIn(BaseModel):
    servings: float = Field(gt=0, le=200)


@router.put("/foods/{food_id}/servings")
def set_split(food_id: int, b: SplitIn, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        ok = c.execute(
            """select 1 from foods f where f.id = %(fid)s and
               (f.owner_id = %(uid)s or f.source_type = 'restaurant'
                or exists (select 1 from user_books ub where ub.book_id = f.book_id and ub.user_id = %(uid)s))""",
            {"fid": food_id, "uid": uid},
        ).fetchone()
        if not ok:
            raise HTTPException(404, "Food not found")
        c.execute(
            """insert into food_prefs (user_id, food_id, servings) values (%s,%s,%s)
               on conflict (user_id, food_id) do update set servings = excluded.servings""",
            (uid, food_id, b.servings),
        )
    return {"ok": True}


class WeightIn(BaseModel):
    total_weight_g: float = Field(gt=0, le=100000)


@router.put("/foods/{food_id}/weight")
def set_total_weight(food_id: int, b: WeightIn, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        ok = c.execute(
            """select 1 from foods f where f.id = %(fid)s and
               (f.owner_id = %(uid)s or f.source_type = 'restaurant'
                or exists (select 1 from user_books ub where ub.book_id = f.book_id and ub.user_id = %(uid)s))""",
            {"fid": food_id, "uid": uid},
        ).fetchone()
        if not ok:
            raise HTTPException(404, "Food not found")
        c.execute(
            """insert into food_prefs (user_id, food_id, total_weight_g) values (%s,%s,%s)
               on conflict (user_id, food_id) do update set total_weight_g = excluded.total_weight_g""",
            (uid, food_id, b.total_weight_g),
        )
    return {"ok": True}


@router.delete("/logs/{log_id}")
def delete_log(log_id: int, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        c.execute("delete from food_logs where id = %s and user_id = %s", (log_id, uid))
    return {"ok": True}


@router.get("/day/{day}")
def day_summary(day: date, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        logs = c.execute(
            """select id, meal_slot, name, servings, calories, protein_g, carbs_g, fat_g, is_estimate
               from food_logs where user_id = %s and date = %s order by id""",
            (uid, day),
        ).fetchall()
    totals = {k: round(sum(float(r[k]) for r in logs), 1) for k in ("calories", "protein_g", "carbs_g", "fat_g")}
    with db.conn() as c:
        exercise = c.execute(
            """select id, type, duration_min, distance_km, kcal_burned
               from exercise_logs where user_id = %s and date = %s order by id""",
            (uid, day),
        ).fetchall()
        eat_back = c.execute(
            "select exercise_eat_back from profiles where user_id = %s", (uid,)
        ).fetchone()
        complete = c.execute(
            "select 1 from complete_days where user_id = %s and date = %s", (uid, day)
        ).fetchone() is not None
    burned = sum(float(x["kcal_burned"]) for x in exercise)
    bonus = round(burned * goals.EAT_BACK[(eat_back or {}).get("exercise_eat_back", "none")])
    try:
        target = _load_goal(uid, day)
        if target["method"] == "adaptive":
            bonus = 0  # measured maintenance already reflects your typical exercise
        target["exercise_bonus"] = bonus
        target["calories"] += bonus
    except HTTPException:
        target = None
    return {"date": day, "logs": logs, "totals": totals, "target": target, "exercise": exercise,
            "exercise_burned": round(burned), "complete": complete, "has_estimates": any(r["is_estimate"] for r in logs)}


@router.delete("/day/{day}/complete")
def unmark_complete(day: date, uid: str = Depends(current_user_id)):
    with db.conn() as c:
        c.execute("delete from complete_days where user_id = %s and date = %s", (uid, day))
    return {"ok": True}


@router.put("/day/{day}/complete")
def mark_complete(day: date, uid: str = Depends(current_user_id)):
    if day > date.today() + timedelta(days=1):
        raise HTTPException(422, "Cannot mark a future day complete")
    with db.conn() as c:
        c.execute(
            "insert into complete_days (user_id, date) values (%s,%s) on conflict do nothing", (uid, day)
        )
    return {"ok": True}
