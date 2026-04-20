from __future__ import annotations

from .db import Database
from .models import Ingredient, IngredientNutrition, NutritionSummary
from .normalization import ingredient_to_grams


class NutritionDataError(ValueError):
    """Raised when required nutrition data is missing from the database row."""


def _first_number(row: dict, keys: list[str]) -> float:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return float(value)
    raise NutritionDataError(f"Missing nutrition column. Expected one of: {', '.join(keys)}")


def _per_100g(row: dict) -> dict[str, float]:
    return {
        "calories": _first_number(row, ["calories_per_100g", "calories"]),
        "protein": _first_number(row, ["protein_per_100g", "protein"]),
        "carbs": _first_number(row, ["carbs_per_100g", "carbs"]),
        "fat": _first_number(row, ["fat_per_100g", "fats", "fat"]),
        "fiber": _first_number(row, ["fiber_per_100g", "fiber"]),
    }


async def calculate_nutrition(
    ingredients: list[Ingredient],
    db: Database,
    ai=None,
) -> NutritionSummary:
    rows: list[IngredientNutrition] = []
    errors: list[str] = []

    for ingredient in ingredients:
        food = db.get_food(ingredient.name)
        if not food:
            errors.append(f"{ingredient.name} food not found in database")
            continue

        try:
            per_100g = _per_100g(food)
        except NutritionDataError as exc:
            errors.append(f"{ingredient.name}: {exc}")
            continue

        grams = ingredient_to_grams(ingredient)
        factor = grams / 100
        rows.append(
            IngredientNutrition(
                name=str(food.get("name", ingredient.name)).lower(),
                quantity=ingredient.quantity,
                unit=ingredient.unit,
                grams_equivalent=round(grams, 2),
                calories=round(per_100g["calories"] * factor, 1),
                protein=round(per_100g["protein"] * factor, 1),
                carbs=round(per_100g["carbs"] * factor, 1),
                fats=round(per_100g["fat"] * factor, 1),
                fiber=round(per_100g["fiber"] * factor, 1),
                accuracy="Database",
                source="Supabase foods",
            )
        )

    return NutritionSummary(
        ingredients=rows,
        total_calories=round(sum(item.calories for item in rows), 1),
        total_protein=round(sum(item.protein for item in rows), 1),
        total_carbs=round(sum(item.carbs for item in rows), 1),
        total_fats=round(sum(item.fats for item in rows), 1),
        total_fiber=round(sum(item.fiber for item in rows), 1),
        has_estimates=False,
        errors=errors,
    )
