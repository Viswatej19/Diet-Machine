from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


Accuracy = Literal["Database"]


class Ingredient(BaseModel):
    name: str = Field(description="Normalized lowercase ingredient name")
    quantity: float = Field(description="Numeric quantity after parsing")
    unit: str = Field(description="Normalized unit: g, ml, or pieces")


class ParsedIngredients(BaseModel):
    ingredients: list[Ingredient]


class IngredientNutrition(BaseModel):
    name: str
    quantity: float
    unit: str
    grams_equivalent: float
    calories: float
    protein: float
    carbs: float
    fats: float
    fiber: float = 0
    accuracy: Accuracy
    source: str


class NutritionSummary(BaseModel):
    ingredients: list[IngredientNutrition]
    total_calories: float
    total_protein: float
    total_carbs: float
    total_fats: float
    total_fiber: float
    has_estimates: bool
    errors: list[str] = Field(default_factory=list)


class Recipe(BaseModel):
    title: str
    ingredients: list[Ingredient]
    steps: list[str]
    calories: float
    protein: float = 0
    carbs: float = 0
    fats: float = 0
    fiber: float = 0
    prep_time_minutes: int


class RecipeList(BaseModel):
    recipes: list[Recipe]


class ParsedValidationResult(BaseModel):
    valid_ingredients: list[Ingredient]
    invalid_ingredients: list[Ingredient]
    errors: list[str] = Field(default_factory=list)


class DailyDietMeal(BaseModel):
    meal_type: Literal["breakfast", "lunch", "dinner", "snacks"]
    items: list[Ingredient]
    calories: float
    protein: float


class DailyDietPlan(BaseModel):
    meals: list[DailyDietMeal]


class UserPreferences(BaseModel):
    calorie_target: float = 2000
    protein_target: float = 100
    diet_type: Literal["veg", "non-veg"] = "veg"
    weight: Optional[float] = None
    goal: Literal["fat loss", "muscle gain", "maintenance"] = "maintenance"


class UserGoals(BaseModel):
    calories: int
    protein: int
    fiber: Optional[int] = None


class DietTargets(BaseModel):
    calories: int
    protein: int
    fiber: int = 30


class DietValidation(BaseModel):
    valid: bool
    actual: dict
    checks: dict


class UserLog(BaseModel):
    id: Optional[str] = None
    input_text: str
    ingredients: list[dict]
    nutrition: dict
    total_calories: float
    recipes: str
    created_at: Optional[datetime] = None


class WeightLog(BaseModel):
    id: Optional[str] = None
    user_id: str
    date: date
    weight: float
