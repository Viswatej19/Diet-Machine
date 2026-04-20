from __future__ import annotations

import re
from difflib import get_close_matches

from .db import Database
from .models import Ingredient, ParsedValidationResult
from .normalization import merge_duplicates
from .openai_service import OpenAIService


UNIT_ALIASES = {
    "g": "g",
    "gm": "g",
    "gms": "g",
    "gram": "g",
    "grams": "g",
    "kg": "g",
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "ml",
    "liter": "ml",
    "liters": "ml",
    "cup": "bowl",
    "cups": "bowl",
    "bowl": "bowl",
    "bowls": "bowl",
    "piece": "pieces",
    "pieces": "pieces",
    "pc": "pieces",
    "pcs": "pieces",
}

ALIASES = {
    "paner": "paneer",
    "panner": "paneer",
    "paneeer": "paneer",
    "rie": "rice",
    "ric": "rice",
    "soa chunks": "soya chunks",
    "soya chunk": "soya chunks",
    "soy chunks": "soya chunks",
    "egg": "eggs",
    "eggs": "eggs",
}

STOPWORDS = {"of", "and", "with"}

QUANTITY_RE = re.compile(r"(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>grams?|gms?|gm|g|kg|ml|milliliters?|liters?|l|cups?|bowls?|pieces?|pcs?|pc)?", re.I)


def parse_ingredient_text(input_text: str) -> list[Ingredient]:
    if not input_text or not input_text.strip():
        return []

    ingredients: list[Ingredient] = []
    for chunk in [part.strip() for part in input_text.split(",")]:
        if not chunk:
            continue
        match = QUANTITY_RE.search(chunk)
        quantity = 100.0
        unit = "g"
        name_text = chunk

        if match:
            quantity = float(match.group("qty"))
            explicit_unit = match.group("unit")
            raw_unit = (explicit_unit or "g").lower()
            unit = UNIT_ALIASES.get(raw_unit, "g")
            name_text = (chunk[: match.start()] + " " + chunk[match.end() :]).strip()
            if raw_unit == "kg":
                quantity *= 1000
            elif raw_unit in {"l", "liter", "liters"}:
                quantity *= 1000
        elif chunk.strip().isdigit():
            ingredients.append(Ingredient(name=chunk.strip(), quantity=float(chunk.strip()), unit="g"))
            continue

        name = normalize_raw_name(name_text)
        if not match and name in {"egg", "eggs"}:
            unit = "pieces"
        if match and not explicit_unit and name in {"egg", "eggs"} and quantity <= 12:
            unit = "pieces"
        if not name:
            name = chunk.strip().lower()
        ingredients.append(Ingredient(name=name, quantity=quantity, unit=unit))

    return merge_duplicates(ingredients)


def normalize_raw_name(name: str) -> str:
    cleaned = re.sub(r"\b(grams?|gms?|gm|kg|ml|milliliters?|liters?|cups?|bowls?|pieces?|pcs?|pc)\b", " ", name.lower())
    cleaned = re.sub(r"[^a-z\s]", " ", cleaned)
    return " ".join(word for word in cleaned.split() if word not in STOPWORDS)


def normalize_name_to_allowed(name: str, allowed_foods: list[str]) -> str | None:
    normalized_allowed = {food.lower(): food for food in allowed_foods}
    candidate = normalize_raw_name(name)
    candidate = ALIASES.get(candidate, candidate)

    if candidate in normalized_allowed:
        return normalized_allowed[candidate]

    prefix_matches = [food for key, food in normalized_allowed.items() if key.startswith(candidate) and candidate]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    close = get_close_matches(candidate, list(normalized_allowed), n=1, cutoff=0.78)
    if close:
        return normalized_allowed[close[0]]
    return None


async def parse_and_validate_ingredients(
    input_text: str,
    db: Database,
    ai: OpenAIService | None = None,
) -> ParsedValidationResult:
    parsed = parse_ingredient_text(input_text)
    if not parsed:
        return ParsedValidationResult(valid_ingredients=[], invalid_ingredients=[], errors=["No ingredients entered."])

    allowed_foods = db.list_food_names()
    if not allowed_foods:
        return ParsedValidationResult(
            valid_ingredients=[],
            invalid_ingredients=parsed,
            errors=["Food database is unavailable or empty. Add foods in Supabase before calculating nutrition."],
        )

    normalized_by_ai: dict[str, str] = {}
    if ai is not None:
        normalized_by_ai = await ai.normalize_food_names([item.name for item in parsed], allowed_foods)

    valid: list[Ingredient] = []
    invalid: list[Ingredient] = []
    errors: list[str] = []
    allowed_lower = {food.lower(): food for food in allowed_foods}

    for item in parsed:
        mapped_name = normalized_by_ai.get(item.name)
        if mapped_name and mapped_name.lower() not in allowed_lower:
            mapped_name = None
        mapped_name = mapped_name or normalize_name_to_allowed(item.name, allowed_foods)

        if not mapped_name:
            invalid.append(item)
            continue
        valid.append(Ingredient(name=allowed_lower[mapped_name.lower()], quantity=item.quantity, unit=item.unit))

    # --- INFINITE REAL-TIME DATABASE PIPELINE ---
    if invalid and ai is not None and ai.available:
        missing_names = list({item.name for item in invalid})
        new_macros = await ai.fetch_missing_foods_macros(missing_names)
        
        if new_macros:
            new_foods_payload = [m.model_dump() for m in new_macros]
            db.insert_foods(new_foods_payload)
            
            # Re-map newly verified items
            valid_names_new = {m.name: m.name for m in new_macros}
            still_invalid = []
            for item in invalid:
                # Attempt loose mapping against the newly hydrated words
                match = normalize_name_to_allowed(item.name, list(valid_names_new.keys()))
                if match:
                    valid.append(Ingredient(name=valid_names_new[match], quantity=item.quantity, unit=item.unit))
                else:
                    still_invalid.append(item)
                    errors.append(f"AI declined to map missing food: {item.name}")
            invalid = still_invalid
        else:
            for item in invalid:
                errors.append(f"{item.name} food not found in database and AI hydration failed.")
    elif invalid:
        for item in invalid:
            errors.append(f"{item.name} food not found in database.")

    return ParsedValidationResult(
        valid_ingredients=merge_duplicates(valid),
        invalid_ingredients=invalid,
        errors=errors,
    )
