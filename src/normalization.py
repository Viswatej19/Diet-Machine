from collections import defaultdict

from .models import Ingredient


BOWL_GRAMS = {
    "rice": 150,
    "cooked rice": 150,
    "dal": 180,
    "curd": 200,
    "oats": 80,
    "salad": 100,
}

PIECE_GRAMS = {
    "egg": 50,
    "eggs": 50,
    "banana": 118,
    "apple": 182,
    "roti": 40,
    "chapati": 40,
    "bread": 25,
}

ML_DENSITY_TO_GRAMS = {
    "oil": 0.92,
    "milk": 1.03,
    "water": 1.0,
    "curd": 1.03,
}


def clean_name(name: str) -> str:
    cleaned = " ".join(name.strip().lower().split())
    if cleaned == "egg":
        return "eggs"
    return cleaned


def ingredient_to_grams(ingredient: Ingredient) -> float:
    name = clean_name(ingredient.name)
    unit = ingredient.unit.lower()
    quantity = float(ingredient.quantity or 0)

    if unit in {"g", "gram", "grams"}:
        return quantity
    if unit in {"ml", "milliliter", "milliliters"}:
        return quantity * ML_DENSITY_TO_GRAMS.get(name, 1.0)
    if unit in {"piece", "pieces", "pc", "pcs"}:
        return quantity * PIECE_GRAMS.get(name, 50)
    if unit in {"bowl", "bowls"}:
        return quantity * BOWL_GRAMS.get(name, 150)
    if unit in {"tsp", "teaspoon", "teaspoons"}:
        return quantity * 5
    if unit in {"tbsp", "tablespoon", "tablespoons"}:
        return quantity * 15
    return quantity


def normalize_ingredient(ingredient: Ingredient) -> Ingredient:
    name = clean_name(ingredient.name)
    unit = ingredient.unit.lower().strip()
    quantity = float(ingredient.quantity or 0)

    if quantity <= 0:
        quantity = 5 if name == "oil" else 100

    if unit in {"gram", "grams"}:
        unit = "g"
    elif unit in {"milliliter", "milliliters"}:
        unit = "ml"
    elif unit in {"piece", "pc", "pcs"}:
        unit = "pieces"

    if unit in {"bowl", "bowls", "tsp", "teaspoon", "teaspoons", "tbsp", "tablespoon", "tablespoons"}:
        grams = ingredient_to_grams(Ingredient(name=name, quantity=quantity, unit=unit))
        return Ingredient(name=name, quantity=round(grams, 2), unit="g")

    return Ingredient(name=name, quantity=quantity, unit=unit or "g")


def merge_duplicates(ingredients: list[Ingredient]) -> list[Ingredient]:
    merged: dict[tuple[str, str], float] = defaultdict(float)
    for ingredient in ingredients:
        item = normalize_ingredient(ingredient)
        merged[(item.name, item.unit)] += item.quantity
    return [
        Ingredient(name=name, quantity=round(quantity, 2), unit=unit)
        for (name, unit), quantity in sorted(merged.items())
    ]
