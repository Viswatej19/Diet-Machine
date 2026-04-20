from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from .db import Database
from .food_parser import parse_and_validate_ingredients
from .models import UserPreferences
from .nutrition import calculate_nutrition
from .openai_service import OpenAIService


QUICK_FOODS = {
    "2 eggs": "2 eggs",
    "100g paneer": "100g paneer",
    "1 cup rice": "1 bowl rice",
    "soya chunks": "50g soya chunks",
}

# Meal-type distribution of daily calorie/macro targets
MEAL_DISTRIBUTION = {
    "breakfast": 0.25,
    "lunch": 0.35,
    "dinner": 0.25,
    "snacks": 0.15,
}

PROTEIN_SOURCES = {
    "veg": ["soya chunks", "paneer", "tofu", "curd", "besan"],
    "non-veg": ["chicken breast", "eggs", "curd", "paneer"],
}

FIBER_SOURCES = ["spinach", "oats", "besan"]
CALORIE_DENSE = ["rice", "oats", "paneer", "oil"]


def calculate_goal_targets(user_goals: dict) -> dict:
    fiber = user_goals.get("fiber") or 30
    return {
        "calories": int(user_goals["calories"]),
        "protein": int(user_goals["protein"]),
        "fiber": int(fiber),
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _food_row(db: Database, name: str) -> Optional[dict]:
    return db.get_food(name)


def _macro(row: dict, key: str) -> float:
    for col in {"calories": ["calories_per_100g", "calories"],
                "protein": ["protein_per_100g", "protein"],
                "fiber": ["fiber_per_100g", "fiber"]}[key]:
        v = row.get(col)
        if v is not None:
            return float(v)
    return 0.0


def _qty_for_macro(row: dict, key: str, target: float) -> float:
    m = _macro(row, key)
    return round((target / m) * 100, 1) if m > 0 else 0.0


def _totals(items: list[dict], db: Database) -> dict[str, float]:
    t = {"calories": 0.0, "protein": 0.0, "fiber": 0.0}
    for item in items:
        row = _food_row(db, item["name"])
        if not row:
            continue
        f = float(item["quantity"]) / 100
        t["calories"] += _macro(row, "calories") * f
        t["protein"] += _macro(row, "protein") * f
        t["fiber"] += _macro(row, "fiber") * f
    return {k: round(v, 1) for k, v in t.items()}


def _set_qty(items: list[dict], name: str, qty: float) -> None:
    qty = max(round(qty, 1), 0)
    for item in items:
        if item["name"] == name:
            item["quantity"] = qty
            return
    if qty > 0:
        items.append({"name": name, "quantity": qty, "unit": "g"})


def _find_food(db: Database, candidates: list[str]):
    for name in candidates:
        row = _food_row(db, name)
        if row:
            return row, name
    return None, None


# ── Core builder ─────────────────────────────────────────────────────────────

async def generate_daily_diet(
    db: Database,
    ai: OpenAIService,
    user_id: str,
    preferences: UserPreferences,
    diet_date: Optional[date] = None,
    targets: Optional[dict] = None,
) -> dict:
    diet_date = diet_date or date.today()

    if targets is None:
        goals = db.get_goals(user_id)
        if not goals:
            return {"meals": [], "validation": None, "errors": ["Please set your goals first."]}
        targets = calculate_goal_targets(goals)

    if not targets.get("calories") or not targets.get("protein"):
        return {"meals": [], "validation": None, "errors": ["Calorie and protein goals are required."]}

    targets.setdefault("fiber", 30)

    try:
        ai_diet = await ai.generate_intelligent_diet(targets, preferences.diet_type)
        meals = []
        actual = {"calories": 0.0, "protein": 0.0, "fiber": 0.0}
        
        for meal in ai_diet.meals:
            meal_dict = {
                "meal_type": meal.meal_type,
                "items": [{"name": i.name, "quantity": i.quantity, "unit": i.unit} for i in meal.items],
                "calories": round(meal.calories, 1),
                "protein": round(meal.protein, 1),
                "fiber": round(meal.fiber, 1)
            }
            meals.append(meal_dict)
            actual["calories"] += meal.calories
            actual["protein"] += meal.protein
            actual["fiber"] += meal.fiber
            
        protein_ok = abs(actual["protein"] - targets["protein"]) <= 15
        calories_ok = abs(actual["calories"] - targets["calories"]) <= 150
        fiber_ok = actual["fiber"] >= targets["fiber"] - 8
        protein_match_pct = round((actual["protein"] / max(targets["protein"], 1)) * 100, 1)
        
        validation = {
            "valid": protein_ok and calories_ok and fiber_ok,
            "actual": {k: round(v, 1) for k, v in actual.items()},
            "protein_match_pct": min(protein_match_pct, 100.0),
            "checks": {"protein_ok": protein_ok, "calories_ok": calories_ok, "fiber_ok": fiber_ok},
        }

        if meals:
            db.save_daily_diet(user_id, diet_date, meals)
            db.save_diet(user_id, diet_date, meals, validation["actual"])

        return {"meals": meals, "validation": validation, "errors": []}

    except Exception as e:
        return {"meals": [], "validation": None, "errors": [f"AI Diet Engine failed to parse: {e}"]}


async def log_food_text(
    db: Database,
    ai: OpenAIService,
    user_id: str,
    meal_type: str,
    input_text: str,
) -> dict:
    validation = await parse_and_validate_ingredients(input_text, db, ai)
    nutrition = await calculate_nutrition(validation.valid_ingredients, db)
    errors = [*validation.errors, *nutrition.errors]
    if validation.valid_ingredients:
        db.log_meal(
            user_id=user_id,
            meal_type=meal_type,
            input_text=input_text,
            ingredients=[i.model_dump() for i in validation.valid_ingredients],
            nutrition=nutrition.model_dump(),
        )
    return {
        "ingredients": [i.model_dump() for i in validation.valid_ingredients],
        "invalid_ingredients": [i.model_dump() for i in validation.invalid_ingredients],
        "nutrition": nutrition.model_dump(),
        "errors": errors,
    }


async def log_quick_food(db, ai, user_id, meal_type, item):
    return await log_food_text(db, ai, user_id, meal_type, QUICK_FOODS[item])


def get_today_summary(db, user_id, selected_date=None):
    return db.get_today_summary(user_id, selected_date)


def get_history(db, user_id, selected_date=None, search=""):
    return db.get_history(user_id, selected_date, search)


def save_weight(db, user_id, weight, log_date=None):
    db.save_weight(user_id, weight, log_date)


def get_progress(db, user_id):
    return db.get_progress(user_id)


def diet_correction(summary: dict, preferences: UserPreferences) -> list[str]:
    suggestions = []
    p_gap = preferences.protein_target - summary.get("total_protein", 0)
    c_gap = preferences.calorie_target - summary.get("total_calories", 0)
    if p_gap > 20:
        if preferences.diet_type == "non-veg":
            suggestions.append("Protein is low — add eggs, chicken breast, or curd.")
        else:
            suggestions.append("Protein is low — add paneer, tofu, curd, or soya chunks.")
    elif p_gap > 5:
        suggestions.append("Protein is close to target — add a small protein snack.")
    if c_gap < -150:
        suggestions.append("Calories above target — keep dinner lighter and reduce rice/oil portions.")
    elif c_gap > 500:
        suggestions.append("Calories still low — add a balanced meal to hit your target.")
    return suggestions or ["Great balance today! Stay consistent and hydrate well."]
