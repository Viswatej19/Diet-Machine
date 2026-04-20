from __future__ import annotations

import asyncio
import json
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings
from .models import Ingredient, ParsedIngredients, RecipeList
from .normalization import merge_duplicates
from .recipe_engine import generate_recipe_from_database_nutrition


class AIMealItem(BaseModel):
    name: str
    quantity: float
    unit: str

class AIMeal(BaseModel):
    meal_type: str
    items: list[AIMealItem]
    calories: float
    protein: float
    fiber: float

class AIDailyDiet(BaseModel):
    meals: list[AIMeal]
    
class AIIndependentRecipe(BaseModel):
    title: str
    calories: float
    protein: float
    prep_time_minutes: int
    steps: list[str]
    
class AINutritionEstimate(BaseModel):
    calories: float
    protein: float
    fiber: float

class AIIndependentRecipeList(BaseModel):
    nutrition_estimate: AINutritionEstimate
    recipes: list[AIIndependentRecipe]

class AIFoodMacro(BaseModel):
    name: str 
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float
    fiber_per_100g: float

class AIFoodMacroList(BaseModel):
    foods: list[AIFoodMacro]

T = TypeVar("T", bound=BaseModel)


class NameNormalization(BaseModel):
    mappings: dict[str, str | None]


class OpenAIService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.has_openai else None

    @property
    def available(self) -> bool:
        return self.client is not None

    async def normalize_food_names(self, names: list[str], allowed_foods: list[str]) -> dict[str, str]:
        if not self.available or not names or not allowed_foods:
            return {}

        original_names = list(names)
        allowed_lower = {food.lower(): food for food in allowed_foods}
        try:
            parsed = await self._structured_call(
                NameNormalization,
                "food_name_normalization",
                (
                    "Map each input food name to exactly one food from the allowed_foods list, or null. "
                    "You may only fix spelling and map synonyms. Do not change quantities, add foods, remove foods, "
                    "invent names, or return a food not present in allowed_foods. Return exactly one mapping per input name."
                ),
                json.dumps({"input_names": original_names, "allowed_foods": allowed_foods}),
            )
        except Exception:
            return {}

        if set(parsed.mappings.keys()) != set(original_names):
            return {}

        safe: dict[str, str] = {}
        for original, mapped in parsed.mappings.items():
            if mapped is None:
                continue
            canonical = allowed_lower.get(mapped.lower())
            if canonical:
                safe[original] = canonical
        return safe

    async def parse_ingredients(self, input_text: str) -> list[Ingredient]:
        # Compatibility helper for older UI paths. Validation happens in food_parser.
        return self._heuristic_parse(input_text)

    async def generate_recipes(self, ingredients: list[Ingredient], nutrition, *_, **__) -> RecipeList:
        # Recipes are deterministic and use already-calculated database nutrition only.
        return generate_recipe_from_database_nutrition(ingredients, nutrition)

    async def generate_intelligent_diet(self, targets: dict, diet_type: str) -> AIDailyDiet:
        if not self.available:
            raise RuntimeError("OpenAI client missing")
        
        prompt = (
            f"Generate a practical Indian diet plan STRICTLY for a {diet_type.upper()} diet.\n"
            f"If Diet type is NON-VEG, you MUST include Chicken, Eggs, or Fish. NEVER provide a pure veg diet for Non-Veg.\n"
            f"Daily Targets: {targets['calories']} kcal, {targets['protein']}g protein, {targets['fiber']}g fiber.\n\n"
            "CRITICAL RULES:\n"
            "1. You MUST hit the protein target EXACTLY (+/- 5g). Do NOT over-allocate protein. If the target is 120g, total protein must be between 115g and 125g.\n"
            "2. Ensure exact mathematical precision: Calories should roughly equal (Protein*4 + Carbs*4 + Fat*9).\n"
            "3. Use practical serving sizes (e.g., Spinach max 50-100g. Meat max 200g per meal).\n"
            "4. For heavy protein goals, specifically utilize Whey Protein, Soya Chunks, Paneer, or Eggs/Chicken heavily to meet macros without exploding calories.\n"
            "5. Return exactly 4 meals: breakfast, lunch, snacks, dinner."
        )
        
        return await self._structured_call(
            AIDailyDiet,
            "generate_indian_diet",
            "You are an elite Indian clinical nutritionist.",
            prompt
        )

    async def generate_independent_recipe(self, raw_text: str, targets: dict, diet_type: str) -> AIIndependentRecipeList:
        if not self.available:
            raise RuntimeError("OpenAI client missing")
            
        prompt = (
            f"The user wants a recipe using loosely these ingredients: '{raw_text}'.\n"
            f"Diet type constraint: {diet_type}.\n"
            f"Goal targets context: {targets['calories']} cal, {targets['protein']} protein.\n\n"
            "1. Estimate the total nutrition (Calories, Protein, Fiber) based on standard cooking amounts of these items.\n"
            "2. Provide 2 distinct, protein-optimized recipes combining these ingredients sensibly.\n"
            "3. Feel free to assume basic pantry staples (spices, light oil, water) exist."
        )
        return await self._structured_call(
            AIIndependentRecipeList,
            "independent_recipe_maker",
            "You are a master chef creating recipes independently of any database.",
            prompt
        )

    async def fetch_missing_foods_macros(self, food_names: list[str]) -> list[AIFoodMacro]:
        if not self.available or not food_names:
            return []
            
        prompt = (
            f"Provide exact nutritional data per 100 grams for the following foods: {', '.join(food_names)}.\n\n"
            "CRITICAL RAILGUARDS AND ACCURACY RULES:\n"
            "1. You MUST use factual USDA FoodData Central or NIN (India) database standards.\n"
            "2. Ensure mathematical validity: Calories should roughly equal (Protein*4 + Carbs*4 + Fat*9).\n"
            "3. If a food is a cooked meal (e.g. 'paneer butter masala', 'chicken tikka'), estimate the standard restaurant/home preparation per 100g accurately.\n"
            "4. NEVER hallucinate. If completely unknown, return reasonable standard estimates for its closest ingredient.\n"
            "5. The 'name' field must be the exact cleaned input name mapped."
        )
        try:
            res = await self._structured_call(
                AIFoodMacroList,
                "fetch_food_macros",
                "You are an elite clinical diet data system strictly outputting accurate USDA/NIN nutrition data per 100g.",
                prompt
            )
            return res.foods
        except Exception:
            return []

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=0.5, max=2))
    async def _structured_call(self, schema: type[T], name: str, system: str, user: str) -> T:
        if not self.client:
            raise RuntimeError("OpenAI client is not configured.")

        response = await self.client.responses.parse(
            model=self.settings.openai_model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text_format=schema,
        )
        parsed = response.output_parsed
        if parsed is None:
            text = getattr(response, "output_text", "")
            try:
                return schema.model_validate_json(text)
            except (ValidationError, ValueError) as exc:
                raise ValueError(f"Invalid JSON for {name}: {exc}") from exc
        return parsed

    def _heuristic_parse(self, input_text: str) -> list[Ingredient]:
        from .food_parser import parse_ingredient_text

        return merge_duplicates(parse_ingredient_text(input_text))


def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)
