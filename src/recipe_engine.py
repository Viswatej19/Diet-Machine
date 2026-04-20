from __future__ import annotations

from .models import Ingredient, NutritionSummary, Recipe, RecipeList


COOKING_STYLES = ["bhurji", "curry", "stir fry", "chilla"]


def generate_recipe_from_database_nutrition(
    ingredients: list[Ingredient],
    nutrition: NutritionSummary,
) -> RecipeList:
    if not ingredients or not nutrition.ingredients:
        return RecipeList(recipes=[])

    names = [item.name.lower() for item in ingredients]
    title, style = _pick_style(names)
    ingredient_names = ", ".join(item.name for item in ingredients)

    steps = [
        f"Measure only these ingredients: {ingredient_names}.",
        f"Cook them as a simple {style} until the main ingredient is done.",
        "Keep heat medium and stir as needed to avoid burning.",
        "Serve immediately and log the full portion shown here.",
    ]

    return RecipeList(
        recipes=[
            Recipe(
                title=title,
                ingredients=ingredients,
                steps=steps,
                calories=nutrition.total_calories,
                protein=nutrition.total_protein,
                carbs=nutrition.total_carbs,
                fats=nutrition.total_fats,
                fiber=nutrition.total_fiber,
                prep_time_minutes=_prep_time(names),
            )
        ]
    )


def _pick_style(names: list[str]) -> tuple[str, str]:
    if "eggs" in names:
        return "Egg Bhurji", "bhurji"
    if "besan" in names:
        return "Besan Chilla", "chilla"
    if any(name in names for name in ["paneer", "tofu", "soya chunks"]):
        if "rice" in names:
            main = next(name for name in names if name in ["paneer", "tofu", "soya chunks"])
            return f"{main.title()} Rice Stir Fry", "stir fry"
        main = next(name for name in names if name in ["paneer", "tofu", "soya chunks"])
        return f"{main.title()} Curry", "curry"
    return f"{names[0].title()} Stir Fry", "stir fry"


def _prep_time(names: list[str]) -> int:
    if "besan" in names:
        return 15
    if "rice" in names:
        return 20
    return 12
