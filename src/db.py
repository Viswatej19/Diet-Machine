from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Optional

from supabase import Client, create_client

from .config import Settings
from .models import UserPreferences


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[Client] = (
            create_client(settings.supabase_url, settings.supabase_key)
            if settings.has_supabase
            else None
        )

    @property
    def available(self) -> bool:
        return self.client is not None

    def get_user(self):
        if not self.client:
            return None
        session = self.client.auth.get_session()
        if not session:
            return None
        try:
            return self.client.auth.get_user(session.access_token)
        except Exception:
            return None

    def sign_in(self, email: str, password: str):
        if not self.client:
            return None
        return self.client.auth.sign_in_with_password({"email": email, "password": password})

    def sign_up(self, email: str, password: str):
        if not self.client:
            return None
        return self.client.auth.sign_up({"email": email, "password": password})

    def sign_in_with_google(self):
        if not self.client:
            return None
        return self.client.auth.sign_in_with_oauth({
            "provider": "google"
        })

    def exchange_code_for_session(self, code: str):
        if not self.client:
            return None
        return self.client.auth.exchange_code_for_session({"auth_code": code})

    def sign_out(self) -> None:
        if self.client:
            self.client.auth.sign_out()

    def get_food(self, name: str) -> Optional[dict[str, Any]]:
        if not self.client:
            return None
        try:
            result = self.client.table("foods").select("*").ilike("name", name.strip()).limit(2).execute()
            return result.data[0] if result.data else None
        except Exception:
            return None

    def search_food_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        if not self.client:
            return []
        try:
            result = (
                self.client.table("foods")
                .select("*")
                .ilike("name", f"{prefix.strip()}%")
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def list_food_names(self) -> list[str]:
        if not self.client:
            return []
        try:
            result = self.client.table("foods").select("name").order("name").execute()
            return [row["name"] for row in result.data or []]
        except Exception:
            return []

    def insert_foods(self, foods: list[dict]) -> None:
        if not self.client or not foods:
            return
        
        payload = []
        for f in foods:
            payload.append({
                "name": str(f.get("name", "")).lower().strip(),
                "calories_per_100g": float(f.get("calories_per_100g", 0)),
                "protein_per_100g": float(f.get("protein_per_100g", 0)),
                "carbs_per_100g": float(f.get("carbs_per_100g", 0)),
                "fat_per_100g": float(f.get("fat_per_100g", 0)),
                "fiber_per_100g": float(f.get("fiber_per_100g", 0)),
            })
        
        try:
            # We ignore conflicts so we never overwrite manual curated rows
            self.client.table("foods").upsert(payload, on_conflict="name", ignore_duplicates=True).execute()
        except Exception:
            pass

    def get_recipes_for_ingredients(self, names: list[str], diet_type: str) -> list[dict[str, Any]]:
        if not self.client:
            return []
        try:
            result = self.client.table("recipes").select("*").limit(20).execute()
        except Exception:
            return []
        recipes = result.data or []
        name_set = {name.lower() for name in names}
        filtered = []
        for recipe in recipes:
            if recipe.get("diet_type") not in {None, "any", diet_type}:
                continue
            ingredients = recipe.get("ingredients") or []
            recipe_names = {str(item.get("name", "")).lower() for item in ingredients if isinstance(item, dict)}
            if name_set & recipe_names:
                filtered.append(recipe)
        return filtered[:2]

    def save_log(self, user_id: str, input_text: str, ingredients: list[dict], nutrition: dict, recipes: str) -> Optional[str]:
        if not self.client:
            return None
        payload = {
            "user_id": user_id,
            "input_text": input_text,
            "ingredients": ingredients,
            "nutrition": nutrition,
            "total_calories": nutrition.get("total_calories", 0),
            "recipes": recipes,
        }
        try:
            result = self.client.table("user_logs").insert(payload).execute()
            return result.data[0]["id"] if result.data else None
        except Exception:
            return None

    def log_meal(
        self,
        user_id: str,
        meal_type: str,
        input_text: str,
        ingredients: list[dict],
        nutrition: dict,
    ) -> Optional[str]:
        if not self.client:
            return None
        payload = {
            "user_id": user_id,
            "meal_type": meal_type,
            "input_text": input_text,
            "ingredients": ingredients,
            "nutrition": nutrition,
            "calories": nutrition.get("total_calories", 0),
            "protein": nutrition.get("total_protein", 0),
            "fiber": nutrition.get("total_fiber", 0),
        }
        try:
            result = self.client.table("meals").insert(payload).execute()
            return result.data[0]["id"] if result.data else None
        except Exception:
            return None

    def list_logs(self, user_id: str, selected_date: Optional[date] = None, search: str = "") -> list[dict[str, Any]]:
        if not self.client:
            return []
        try:
            result = self.client.table("user_logs").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        except Exception:
            return []
        logs = result.data or []
        if selected_date:
            logs = [log for log in logs if str(log.get("created_at", "")).startswith(selected_date.isoformat())]
        if search:
            search_lower = search.lower()
            logs = [log for log in logs if search_lower in json.dumps(log, default=str).lower()]
        return logs

    def get_history(self, user_id: str, selected_date: Optional[date] = None, search: str = "") -> list[dict[str, Any]]:
        if not self.client:
            return []
        try:
            result = (
                self.client.table("meals")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
        except Exception:
            return []
        meals = result.data or []
        if selected_date:
            meals = [meal for meal in meals if str(meal.get("created_at", "")).startswith(selected_date.isoformat())]
        if search:
            search_lower = search.lower()
            meals = [meal for meal in meals if search_lower in json.dumps(meal, default=str).lower()]
        return meals

    def get_today_summary(self, user_id: str, selected_date: Optional[date] = None) -> dict[str, Any]:
        selected_date = selected_date or datetime.now(timezone.utc).date()
        meals = self.get_history(user_id, selected_date=selected_date)
        total_calories = round(sum(float(meal.get("calories") or 0) for meal in meals), 1)
        total_protein = round(sum(float(meal.get("protein") or 0) for meal in meals), 1)
        total_fiber = round(sum(float(meal.get("fiber") or 0) for meal in meals), 1)
        return {
            "date": selected_date,
            "meals": meals,
            "total_calories": total_calories,
            "total_protein": total_protein,
            "total_fiber": total_fiber,
        }

    def update_log(self, user_id: str, log_id: str, input_text: str) -> None:
        if self.client:
            try:
                self.client.table("user_logs").update({"input_text": input_text}).eq("id", log_id).eq("user_id", user_id).execute()
            except Exception:
                return

    def delete_log(self, user_id: str, log_id: str) -> None:
        if self.client:
            try:
                self.client.table("user_logs").delete().eq("id", log_id).eq("user_id", user_id).execute()
            except Exception:
                return

    def update_meal(self, user_id: str, meal_id: str, meal_type: str, input_text: str) -> None:
        if self.client:
            try:
                self.client.table("meals").update({"meal_type": meal_type, "input_text": input_text}).eq("id", meal_id).eq("user_id", user_id).execute()
            except Exception:
                return

    def delete_meal(self, user_id: str, meal_id: str) -> None:
        if self.client:
            try:
                self.client.table("meals").delete().eq("id", meal_id).eq("user_id", user_id).execute()
            except Exception:
                return

    def get_preferences(self, user_id: Optional[str] = None) -> UserPreferences:
        if not self.client:
            return UserPreferences()
        user_id = user_id or self.settings.app_user_id
        try:
            result = (
                self.client.table("user_preferences")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
        except Exception:
            return UserPreferences()
        if not result.data:
            return UserPreferences()
        row = result.data[0]
        return UserPreferences(
            calorie_target=row.get("calorie_target", 2000),
            protein_target=row.get("protein_target", 100),
            diet_type=row.get("diet_type", "veg"),
            weight=row.get("weight"),
            goal=row.get("goal", "maintenance"),
        )

    def save_preferences(self, preferences: UserPreferences, user_id: Optional[str] = None) -> None:
        if not self.client:
            return
        user_id = user_id or self.settings.app_user_id
        payload = {
            "user_id": user_id,
            "calorie_target": int(preferences.calorie_target),
            "protein_target": int(preferences.protein_target),
            "diet_type": preferences.diet_type,
            "weight": float(preferences.weight) if preferences.weight else None,
            "goal": preferences.goal,
        }
        try:
            self.client.table("user_preferences").upsert(payload, on_conflict="user_id").execute()
        except Exception as e:
            import streamlit as st
            st.error(f"Failed to save preferences to DB: {e}")

    def get_goals(self, user_id: str) -> Optional[dict[str, Any]]:
        if not self.client:
            return None
        try:
            result = (
                self.client.table("user_goals")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if not result.data:
                return None
            row = result.data[0]
            if not row.get("calories") and row.get("calorie_target"):
                row["calories"] = row["calorie_target"]
            if not row.get("protein") and row.get("protein_target"):
                row["protein"] = row["protein_target"]
            return row
        except Exception:
            return None

    def save_goals(self, user_id: str, calories: int, protein: int, fiber: Optional[int] = None) -> None:
        if not self.client:
            return
        payload = {
            "user_id": user_id,
            "calories": int(calories),
            "protein": int(protein),
            "fiber": int(fiber) if fiber else 30,
        }
        try:
            self.client.table("user_goals").upsert(payload, on_conflict="user_id").execute()
        except Exception as e:
            import streamlit as st
            st.error(f"Failed to save goals to DB: {e}")

    def save_daily_diet(self, user_id: str, diet_date: date, meals: list[dict[str, Any]]) -> None:
        if not self.client:
            return
        try:
            self.client.table("daily_diets").delete().eq("user_id", user_id).eq("date", diet_date.isoformat()).execute()
        except Exception:
            return
        payload = [
            {
                "user_id": user_id,
                "date": diet_date.isoformat(),
                "meal_type": meal["meal_type"],
                "items": meal.get("items", []),
                "calories": meal.get("calories", 0),
                "protein": meal.get("protein", 0),
                "fiber": meal.get("fiber", 0),
            }
            for meal in meals
        ]
        if payload:
            try:
                self.client.table("daily_diets").insert(payload).execute()
            except Exception:
                return

    def get_daily_diet(self, user_id: str, diet_date: Optional[date] = None) -> list[dict[str, Any]]:
        if not self.client:
            return []
        diet_date = diet_date or datetime.now(timezone.utc).date()
        try:
            result = (
                self.client.table("daily_diets")
                .select("*")
                .eq("user_id", user_id)
                .eq("date", diet_date.isoformat())
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def save_diet_template(self, user_id: str, name: str, meals: list[dict[str, Any]]) -> Optional[str]:
        if not self.client:
            return None
        payload = {"user_id": user_id, "name": name, "meals": meals, "use_daily": True}
        try:
            result = self.client.table("diet_templates").insert(payload).execute()
            return result.data[0]["id"] if result.data else None
        except Exception:
            return None

    def list_diet_templates(self, user_id: str) -> list[dict[str, Any]]:
        if not self.client:
            return []
        try:
            result = (
                self.client.table("diet_templates")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def save_diet(self, user_id: str, diet_date: date, meals: list[dict[str, Any]], actual: dict[str, Any]) -> Optional[str]:
        if not self.client:
            return None
        payload = {
            "user_id": user_id,
            "date": diet_date.isoformat(),
            "diet_json": {"meals": meals},
            "calories": int(round(float(actual.get("calories", 0)))),
            "protein": int(round(float(actual.get("protein", 0)))),
            "fiber": int(round(float(actual.get("fiber", 0)))),
        }
        try:
            self.client.table("diet_history").delete().eq("user_id", user_id).eq("date", diet_date.isoformat()).execute()
            result = self.client.table("diet_history").insert(payload).execute()
            return result.data[0]["id"] if result.data else None
        except Exception:
            return None

    def get_diet_history(self, user_id: str, selected_date: Optional[date] = None) -> list[dict[str, Any]]:
        if not self.client:
            return []
        try:
            query = self.client.table("diet_history").select("*").eq("user_id", user_id).order("date", desc=True)
            if selected_date:
                query = query.eq("date", selected_date.isoformat())
            result = query.execute()
            return result.data or []
        except Exception:
            return []

    def save_food_log(
        self,
        user_id: str,
        food_name: str,
        calories: float,
        protein: float,
        fiber: float,
        log_date: Optional[date] = None,
    ) -> Optional[str]:
        if not self.client:
            return None
        log_date = log_date or datetime.now(timezone.utc).date()
        payload = {
            "user_id": user_id,
            "food_name": food_name,
            "calories": calories,
            "protein": protein,
            "fiber": fiber,
            "date": log_date.isoformat(),
        }
        try:
            result = self.client.table("food_logs").insert(payload).execute()
            return result.data[0]["id"] if result.data else None
        except Exception:
            return None

    def save_weight(self, user_id: str, weight: float, log_date: Optional[date] = None) -> None:
        if not self.client:
            return
        log_date = log_date or datetime.now(timezone.utc).date()
        payload = {"user_id": user_id, "date": log_date.isoformat(), "weight": weight}
        try:
            self.client.table("weight_logs").upsert(payload, on_conflict="user_id,date").execute()
        except Exception:
            return

    def get_progress(self, user_id: str) -> list[dict[str, Any]]:
        if not self.client:
            return []
        try:
            result = (
                self.client.table("weight_logs")
                .select("*")
                .eq("user_id", user_id)
                .order("date", desc=False)
                .execute()
            )
            return result.data or []
        except Exception:
            return []
