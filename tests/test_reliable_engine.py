from __future__ import annotations

import asyncio

import pytest

from src.food_parser import parse_and_validate_ingredients, parse_ingredient_text
from src.diet_system import calculate_goal_targets, generate_daily_diet, validate_diet
from src.models import Ingredient
from src.nutrition import calculate_nutrition
from src.recipe_engine import generate_recipe_from_database_nutrition


FOODS = {
    "paneer": {"name": "paneer", "calories_per_100g": 265, "protein_per_100g": 18.3, "carbs_per_100g": 1.2, "fat_per_100g": 20.8, "fiber_per_100g": 0},
    "rice": {"name": "rice", "calories_per_100g": 130, "protein_per_100g": 2.7, "carbs_per_100g": 28.2, "fat_per_100g": 0.3, "fiber_per_100g": 0.4},
    "soya chunks": {"name": "soya chunks", "calories_per_100g": 345, "protein_per_100g": 52, "carbs_per_100g": 33, "fat_per_100g": 0.5, "fiber_per_100g": 13},
    "eggs": {"name": "eggs", "calories_per_100g": 143, "protein_per_100g": 12.6, "carbs_per_100g": 0.7, "fat_per_100g": 9.5, "fiber_per_100g": 0},
    "tofu": {"name": "tofu", "calories_per_100g": 144, "protein_per_100g": 17.3, "carbs_per_100g": 2.8, "fat_per_100g": 8.7, "fiber_per_100g": 2.3},
    "besan": {"name": "besan", "calories_per_100g": 387, "protein_per_100g": 22.4, "carbs_per_100g": 57.8, "fat_per_100g": 6.7, "fiber_per_100g": 10.8},
    "curd": {"name": "curd", "calories_per_100g": 98, "protein_per_100g": 11, "carbs_per_100g": 3.4, "fat_per_100g": 4.3, "fiber_per_100g": 0},
    "spinach": {"name": "spinach", "calories_per_100g": 23, "protein_per_100g": 2.9, "carbs_per_100g": 3.6, "fat_per_100g": 0.4, "fiber_per_100g": 2.2},
    "oil": {"name": "oil", "calories_per_100g": 884, "protein_per_100g": 0, "carbs_per_100g": 0, "fat_per_100g": 100, "fiber_per_100g": 0},
    "oats": {"name": "oats", "calories_per_100g": 389, "protein_per_100g": 16.9, "carbs_per_100g": 66.3, "fat_per_100g": 6.9, "fiber_per_100g": 10.6},
    "chicken breast": {"name": "chicken breast", "calories_per_100g": 165, "protein_per_100g": 31, "carbs_per_100g": 0, "fat_per_100g": 3.6, "fiber_per_100g": 0},
}


class FakeDB:
    def list_food_names(self):
        return sorted(FOODS)

    def get_food(self, name):
        return FOODS.get(name.lower())

    def search_food_prefix(self, prefix, limit=10):
        return [row for name, row in FOODS.items() if name.startswith(prefix.lower())][:limit]

    def get_goals(self, user_id):
        return {"calories": 1200, "protein": 100, "fiber": None}

    def save_daily_diet(self, *args, **kwargs):
        return None

    def save_diet(self, *args, **kwargs):
        return None


class NoNutritionAI:
    async def normalize_food_names(self, names, allowed_foods):
        return {}

    async def estimate_nutrition(self, ingredient):
        raise AssertionError("AI nutrition estimation must never be called")


class HallucinatingAI(NoNutritionAI):
    async def normalize_food_names(self, names, allowed_foods):
        return {names[0]: "pizza", "extra food": "paneer"}


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize(
    "raw, expected_name, expected_qty, expected_unit",
    [
        ("paner", "paneer", 100, "g"),
        ("rie", "rice", 100, "g"),
        ("soa chunks", "soya chunks", 100, "g"),
        ("100 g paneer", "paneer", 100, "g"),
        ("2 eggs", "eggs", 2, "pieces"),
        ("100g paner", "paneer", 100, "g"),
        ("paneer 100g", "paneer", 100, "g"),
        ("100 grams paneer", "paneer", 100, "g"),
        ("soa chunks 50g", "soya chunks", 50, "g"),
        ("80 grams of rie", "rice", 80, "g"),
        ("g curd", "curd", 100, "g"),
        ("1 cup rice", "rice", 150, "g"),
    ],
)
def test_ingredient_parsing_and_mapping(raw, expected_name, expected_qty, expected_unit):
    result = run(parse_and_validate_ingredients(raw, FakeDB(), NoNutritionAI()))
    assert not result.errors
    assert len(result.valid_ingredients) == 1
    item = result.valid_ingredients[0]
    assert item.name == expected_name
    assert item.quantity == pytest.approx(expected_qty)
    assert item.unit == expected_unit


@pytest.mark.parametrize(
    "ingredient, expected_calories, expected_protein",
    [
        (Ingredient(name="paneer", quantity=100, unit="g"), 265, 18.3),
        (Ingredient(name="tofu", quantity=100, unit="g"), 144, 17.3),
        (Ingredient(name="besan", quantity=100, unit="g"), 387, 22.4),
        (Ingredient(name="rice", quantity=50, unit="g"), 65, 1.35),
        (Ingredient(name="soya chunks", quantity=50, unit="g"), 172.5, 26),
        (Ingredient(name="eggs", quantity=2, unit="pieces"), 143, 12.6),
        (Ingredient(name="curd", quantity=200, unit="g"), 196, 22),
        (Ingredient(name="spinach", quantity=100, unit="g"), 23, 2.9),
        (Ingredient(name="oats", quantity=60, unit="g"), 233.4, 10.14),
        (Ingredient(name="chicken breast", quantity=180, unit="g"), 297, 55.8),
    ],
)
def test_nutrition_accuracy_database_only(ingredient, expected_calories, expected_protein):
    result = run(calculate_nutrition([ingredient], FakeDB(), NoNutritionAI()))
    assert not result.errors
    assert result.has_estimates is False
    assert result.total_calories == pytest.approx(expected_calories, rel=0.10)
    assert result.total_protein == pytest.approx(expected_protein, rel=0.10)
    assert result.ingredients[0].accuracy == "Database"


@pytest.mark.parametrize(
    "raw, valid_names, invalid_count",
    [
        ("100g paneer", ["paneer"], 0),
        ("100g paner", ["paneer"], 0),
        ("100 grams paneer", ["paneer"], 0),
        ("paneer 100g", ["paneer"], 0),
        ("100g paneer, 50g rice", ["paneer", "rice"], 0),
        ("100g tofu, 100g besan", ["besan", "tofu"], 0),
        ("soa chunks 50g", ["soya chunks"], 0),
        ("randomfood 100g", [], 1),
        (" ", [], 0),
        ("100g paneer, abc", ["paneer"], 1),
        ("100", [], 1),
        ("paneer", ["paneer"], 0),
    ],
)
def test_full_input_edge_cases(raw, valid_names, invalid_count):
    parsed = run(parse_and_validate_ingredients(raw, FakeDB(), NoNutritionAI()))
    nutrition = run(calculate_nutrition(parsed.valid_ingredients, FakeDB(), NoNutritionAI()))
    assert [item.name for item in parsed.valid_ingredients] == valid_names
    assert len(parsed.invalid_ingredients) == invalid_count
    assert nutrition.has_estimates is False
    if valid_names:
        assert nutrition.total_calories > 0
    if not raw.strip():
        assert parsed.errors == ["No ingredients entered."]


def test_hallucinated_ai_mapping_is_rejected_or_overridden_safely():
    parsed = run(parse_and_validate_ingredients("100g paner", FakeDB(), HallucinatingAI()))
    assert [item.name for item in parsed.valid_ingredients] == ["paneer"]
    assert all(item.name != "pizza" for item in parsed.valid_ingredients)


def test_goal_targets_default_fiber():
    assert calculate_goal_targets({"calories": 1200, "protein": 100}) == {
        "calories": 1200,
        "protein": 100,
        "fiber": 30,
    }


def test_generated_diet_validates_against_targets():
    from src.models import UserPreferences

    targets = {"calories": 1200, "protein": 100, "fiber": 30}
    result = run(generate_daily_diet(FakeDB(), NoNutritionAI(), "user-id", UserPreferences(diet_type="veg"), targets=targets))
    assert result["validation"]["valid"] is True
    assert result["validation"]["checks"] == {
        "protein_ok": True,
        "calories_ok": True,
        "fiber_ok": True,
    }
    assert abs(result["validation"]["actual"]["protein"] - 100) <= 5
    assert abs(result["validation"]["actual"]["calories"] - 1200) <= 50
    assert result["validation"]["actual"]["fiber"] >= 30


@pytest.mark.parametrize(
    "ingredients, title_part",
    [
        ([Ingredient(name="eggs", quantity=2, unit="pieces")], "Bhurji"),
        ([Ingredient(name="besan", quantity=100, unit="g")], "Chilla"),
        ([Ingredient(name="paneer", quantity=100, unit="g")], "Curry"),
        ([Ingredient(name="tofu", quantity=100, unit="g")], "Curry"),
        ([Ingredient(name="soya chunks", quantity=50, unit="g")], "Curry"),
        ([Ingredient(name="paneer", quantity=100, unit="g"), Ingredient(name="rice", quantity=50, unit="g")], "Stir Fry"),
        ([Ingredient(name="tofu", quantity=100, unit="g"), Ingredient(name="rice", quantity=50, unit="g")], "Stir Fry"),
        ([Ingredient(name="rice", quantity=150, unit="g")], "Stir Fry"),
        ([Ingredient(name="spinach", quantity=100, unit="g")], "Stir Fry"),
        ([Ingredient(name="chicken breast", quantity=180, unit="g")], "Stir Fry"),
    ],
)
def test_recipe_generation_uses_only_validated_ingredients(ingredients, title_part):
    nutrition = run(calculate_nutrition(ingredients, FakeDB(), NoNutritionAI()))
    recipes = generate_recipe_from_database_nutrition(ingredients, nutrition)
    assert len(recipes.recipes) == 1
    recipe = recipes.recipes[0]
    assert title_part in recipe.title
    assert recipe.calories == nutrition.total_calories
    assert recipe.protein == nutrition.total_protein
    assert [item.name for item in recipe.ingredients] == [item.name for item in ingredients]
