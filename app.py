from datetime import date

import pandas as pd
import streamlit as st

from src.config import get_settings
from src.db import Database
from src.diet_system import (
    QUICK_FOODS,
    calculate_goal_targets,
    diet_correction,
    generate_daily_diet,
    get_history,
    get_progress,
    get_today_summary,
    log_food_text,
    log_quick_food,
    save_weight,
)
from src.food_parser import parse_and_validate_ingredients
from src.models import UserPreferences
from src.nutrition import calculate_nutrition
from src.openai_service import OpenAIService, run_async

st.set_page_config(page_title="Diet Machine", page_icon="🥗", layout="wide")

MEAL_TYPES = ["breakfast", "lunch", "dinner", "snacks"]


# ─────────────────────────────────────────────────────────────────────────────
# Services / session helpers
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_app_services():
    settings = get_settings()
    return settings, Database(settings), OpenAIService(settings)


def set_page(name: str) -> None:
    st.session_state.page = name


def auth_ui(db: Database) -> None:
    st.title("🥗 Diet Machine")
    if not db.available:
        st.error("Supabase is required for login. Add SUPABASE_URL and SUPABASE_KEY in .env.")
        return

    # Handle Google OAuth code exchange
    auth_code = st.query_params.get("code")
    auth_error = st.query_params.get("error_description")
    
    if auth_error:
        st.error(f"OAuth Error: {auth_error.replace('+', ' ')}")
        st.query_params.clear()
        
    elif auth_code:
        try:
            db.exchange_code_for_session(auth_code)
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Google login failed or session expired: {e}")
            st.query_params.clear()

    st.markdown("### Sign in to continue")
    st.divider()

    # Google login
    if st.button("🔵  Continue with Google", use_container_width=True):
        try:
            response = db.sign_in_with_google()
            url = getattr(response, "url", None)
            if url:
                st.link_button("Open Google Login →", url, use_container_width=True)
            else:
                st.warning("Google login unavailable — use email login.")
        except Exception:
            st.warning("Google login failed. Use email login.")

    st.divider()

    mode = st.radio("Account", ["Login", "Create account"], horizontal=True, label_visibility="collapsed")
    email = st.text_input("Email", placeholder="you@example.com")
    password = st.text_input("Password", type="password")

    if st.button(mode, type="primary", use_container_width=True):
        if not email.strip() or not password.strip():
            st.error("Email and password are required.")
            return
        if len(password) < 6:
            st.error("Password must be at least 6 characters.")
            return
        
        try:
            if mode == "Login":
                res = db.sign_in(email.strip(), password)
                if not getattr(res, "user", None):
                    st.error("Invalid credentials. Please check your email and password.")
                    return
                # Login successful, session loaded in memory.
                st.rerun()
            else:
                res = db.sign_up(email.strip(), password)
                if not getattr(res, "user", None):
                    st.error("Signup failed. Ensure email is unique and valid.")
                    return
                # If Supabase gives a user but no session, they need to log in manually.
                if getattr(res, "session", None) is None:
                    st.success("🎉 Account created successfully! Please switch to 'Login' to sign in.")
                    return
                st.rerun()
        except Exception as exc:
            err_str = str(exc)
            if "already registered" in err_str.lower() or "already exists" in err_str.lower():
                st.error("Duplicate email signup: A user with this email already exists.")
            elif "invalid login credentials" in err_str.lower():
                st.error("Invalid credentials.")
            else:
                st.error(f"Authentication failed: {exc}")


def require_user(db: Database):
    if "user" not in st.session_state:
        st.session_state.user = None
        
    try:
        auth_resp = db.get_user()
    except Exception as e:
        auth_resp = None
        st.error(f"Error fetching user session: {e}")

    if not auth_resp:
        st.session_state.user = None
        auth_ui(db)
        st.stop()
        
    st.session_state.user = auth_resp.user
    return auth_resp.user


def current_context():
    settings, db, ai = get_app_services()
    user = require_user(db)
    return settings, db, ai, user.id, db.get_preferences(user.id)


def show_connection_status() -> None:
    settings, db, _, _, _ = current_context()
    if not settings.has_openai:
        st.info("ℹ️ OpenAI key not configured — local parsing active.")
    if not db.available:
        st.warning("⚠️ Supabase not configured — nutrition, saving and history are unavailable.")


# ─────────────────────────────────────────────────────────────────────────────
# Goals inline form (reusable as popup-style expander)
# ─────────────────────────────────────────────────────────────────────────────

def goals_form_inline(db: Database, user_id: str, preferences: UserPreferences, key_prefix: str = "") -> bool:
    """
    Renders a goals form inline (used both in Goals page and as a popup).
    Returns True when goals were just saved.
    """
    existing = db.get_goals(user_id) or {}
    diet_type = st.radio(
        "Diet preference",
        ["veg", "non-veg"],
        index=0 if preferences.diet_type == "veg" else 1,
        horizontal=True,
        key=f"{key_prefix}_diet_type",
    )
    col1, col2, col3 = st.columns(3)
    calorie_target = col1.number_input(
        "Calories :red[*]",
        min_value=800,
        max_value=6000,
        value=int(existing.get("calories") or existing.get("calorie_target") or 2000),
        step=50,
        key=f"{key_prefix}_calories",
        help="Required – your daily calorie target",
    )
    protein_target = col2.number_input(
        "Protein (g) :red[*]",
        min_value=30,
        max_value=500,
        value=int(existing.get("protein") or existing.get("protein_target") or 100),
        step=5,
        key=f"{key_prefix}_protein",
        help="Required – your daily protein target in grams",
    )
    fiber_target = col3.number_input(
        "Fiber (g)",
        min_value=10,
        max_value=100,
        value=int(existing.get("fiber") or 30),
        step=1,
        key=f"{key_prefix}_fiber",
        help="Optional – minimum 30g recommended",
    )
    if st.button("Save Goals", type="primary", use_container_width=True, key=f"{key_prefix}_save"):
        if not calorie_target or not protein_target:
            st.error("Calories :red[*] and Protein :red[*] are required.")
            return False
        db.save_goals(user_id, calorie_target, protein_target, fiber_target)
        db.save_preferences(
            UserPreferences(
                calorie_target=calorie_target,
                protein_target=protein_target,
                diet_type=diet_type,
                weight=preferences.weight,
                goal=preferences.goal,
            ),
            user_id,
        )
        st.success("✅ Goals saved!")
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Shared widgets
# ─────────────────────────────────────────────────────────────────────────────

def score_percent(consumed: float, target: float) -> float:
    if target <= 0:
        return 0
    return min(round((consumed / target) * 100, 1), 100)


def render_big_metric(label: str, value: str, helper: str = "") -> None:
    st.markdown(f"**{label}**")
    st.markdown(f"## {value}")
    if helper:
        st.caption(helper)


def render_daily_diet(meals: list[dict]) -> None:
    if not meals:
        st.info("No diet plan saved for today yet.")
        return
    order = {m: i for i, m in enumerate(MEAL_TYPES)}
    for meal in sorted(meals, key=lambda r: order.get(r.get("meal_type", ""), 99)):
        with st.container(border=True):
            st.subheader(str(meal.get("meal_type", "meal")).title())
            col1, col2, col3 = st.columns(3)
            col1.metric("Calories", f"{float(meal.get('calories') or 0):.0f} kcal")
            col2.metric("Protein", f"{float(meal.get('protein') or 0):.1f} g")
            col3.metric("Fiber", f"{float(meal.get('fiber') or 0):.1f} g")
            for item in meal.get("items", []):
                if isinstance(item, dict):
                    st.write(f"• {item.get('quantity', '')} {item.get('unit', 'g')}  {item.get('name', '')}")
                else:
                    st.write(f"• {item}")


def show_validation(targets: dict, validation: dict) -> None:
    actual = validation.get("actual", {})
    checks = validation.get("checks", {})
    pct = validation.get("protein_match_pct", 0)

    st.subheader("🎯 Target vs. Actual")
    col1, col2, col3 = st.columns(3)

    # Protein – highlight whether it matches
    p_ok = checks.get("protein_ok", False)
    col1.metric(
        "Protein",
        f"{actual.get('protein', 0):.1f} g",
        f"Target {targets['protein']}g — {'✅ Match' if p_ok else '⚠️ Off'}",
        delta_color="normal" if p_ok else "inverse",
    )
    col2.metric(
        "Fiber",
        f"{actual.get('fiber', 0):.1f} g",
        f"Target ≥{targets['fiber']}g — {'✅ OK' if checks.get('fiber_ok') else '⚠️ Low'}",
        delta_color="normal" if checks.get("fiber_ok") else "inverse",
    )
    col3.metric(
        "Calories",
        f"{actual.get('calories', 0):.0f} kcal",
        f"Target {targets['calories']} — {'✅ OK' if checks.get('calories_ok') else '⚠️ Off'}",
        delta_color="normal" if checks.get("calories_ok") else "inverse",
    )

    # Protein match meter
    st.caption(f"Protein match: **{pct}%** of your {targets['protein']}g target")
    st.progress(min(pct / 100, 1.0))

    if validation.get("valid"):
        st.success("✅ Diet plan meets all your targets!")
    else:
        missing = []
        if not checks.get("protein_ok"):
            missing.append(f"protein off by {abs(actual.get('protein', 0) - targets['protein']):.1f}g")
        if not checks.get("calories_ok"):
            missing.append(f"calories off by {abs(actual.get('calories', 0) - targets['calories']):.0f} kcal")
        if not checks.get("fiber_ok"):
            missing.append(f"fiber {actual.get('fiber', 0):.1f}g < {targets['fiber']}g target")
        st.warning("⚠️ Plan is close but " + "; ".join(missing) + ". Consider tweaking portions.")


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

def dashboard_page() -> None:
    _, db, _, user_id, preferences = current_context()
    st.title("🥗 Dashboard")
    st.caption("Your daily diet cockpit.")
    show_connection_status()

    summary = get_today_summary(db, user_id)
    cal_score = score_percent(summary["total_calories"], preferences.calorie_target)
    prot_score = score_percent(summary["total_protein"], preferences.protein_target)
    diet_score = round((cal_score + prot_score) / 2, 1)

    st.subheader("Today's Summary")
    col1, col2, col3 = st.columns(3)
    with col1:
        render_big_metric("Calories", f"{summary['total_calories']:.0f} / {preferences.calorie_target:.0f}", "consumed / target")
        st.progress(cal_score / 100)
    with col2:
        render_big_metric("Protein", f"{summary['total_protein']:.1f} / {preferences.protein_target:.0f}g", "consumed / target")
        st.progress(prot_score / 100)
    with col3:
        render_big_metric("Diet Score", f"{diet_score:.0f}%", "goal completion")
        st.progress(diet_score / 100)

    st.subheader("Quick Actions")
    a1, a2, a3 = st.columns(3)

    # "Generate Today Diet" button with goals-check popup
    if a1.button("🍱 Generate Today Diet", use_container_width=True, type="primary"):
        goals = db.get_goals(user_id)
        if not goals:
            st.session_state["show_goals_popup"] = True
        else:
            set_page("Generate Diet")
            st.rerun()

    a2.button("📝 Log Food", use_container_width=True, on_click=set_page, args=("Log Food",))
    a3.button("📊 View History", use_container_width=True, on_click=set_page, args=("History",))

    # Inline goals popup when no goals exist
    if st.session_state.get("show_goals_popup"):
        with st.container(border=True):
            st.warning("⚠️ You haven't set your goals yet. Set them here to generate your diet plan.")
            st.subheader("Set Your Goals")
            saved = goals_form_inline(db, user_id, preferences, key_prefix="dash_goals")
            if saved:
                st.session_state["show_goals_popup"] = False
                set_page("Generate Diet")
                st.rerun()
            if st.button("Cancel", key="dash_goals_cancel"):
                st.session_state["show_goals_popup"] = False
                st.rerun()

    st.subheader("💡 Suggestions for Today")
    for suggestion in diet_correction(summary, preferences):
        st.info(suggestion)

    st.subheader("Today's Logged Meals")
    meals = summary.get("meals", [])
    if meals:
        for meal in meals:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                col1.write(f"**{meal.get('meal_type', '').title()}**")
                col1.write(meal.get("input_text"))
                col2.metric("Cal", f"{float(meal.get('calories') or 0):.0f}")
                col2.metric("Prot", f"{float(meal.get('protein') or 0):.1f}g")
    else:
        st.info("No food logged today. Use **Log Food** to add your first meal.")

    st.subheader("Today's Diet Plan")
    render_daily_diet(db.get_daily_diet(user_id))


def generate_diet_page() -> None:
    _, db, ai, user_id, preferences = current_context()
    st.title("🍱 Generate Diet")
    st.caption("One click creates breakfast, lunch, dinner, and snacks matched to your exact targets.")
    show_connection_status()

    goals = db.get_goals(user_id)

    # ── Goals popup when missing ──────────────────────────────────────────────
    if not goals:
        with st.container(border=True):
            st.warning("⚠️ You need to set goals before generating a diet plan.")
            st.subheader("Set Your Goals")
            saved = goals_form_inline(db, user_id, preferences, key_prefix="gen_goals")
            if saved:
                st.rerun()
        return

    targets = calculate_goal_targets(goals)

    # ── Target display ────────────────────────────────────────────────────────
    st.subheader("📌 Your Targets")
    col1, col2, col3 = st.columns(3)
    col1.metric("Calories Target", f"{targets['calories']} kcal")
    col2.metric("Protein Target", f"{targets['protein']} g")
    col3.metric("Fiber Target (min)", f"{targets['fiber']} g")

    # ── Generate button ───────────────────────────────────────────────────────
    generating = st.session_state.get("generating_diet", False)
    if st.button(
        "⚡ Generate Today's Diet Plan",
        type="primary",
        use_container_width=True,
        disabled=generating,
    ):
        st.session_state["generating_diet"] = True
        with st.spinner("Building your personalised diet plan..."):
            result = run_async(generate_daily_diet(db, ai, user_id, preferences, targets=targets))
            st.session_state["generated_daily_diet"] = result.get("meals", [])
            st.session_state["diet_validation"] = result.get("validation")
            st.session_state["generating_diet"] = False
            if result.get("meals"):
                st.success("✅ Today's diet generated and saved!")
            else:
                for error in result.get("errors", ["Diet generation failed. Try again."]):
                    st.error(error)

    # ── Show plan ─────────────────────────────────────────────────────────────
    meals = st.session_state.get("generated_daily_diet") or db.get_daily_diet(user_id)
    render_daily_diet(meals)

    # ── Validation / protein match ────────────────────────────────────────────
    validation = st.session_state.get("diet_validation")
    if validation:
        show_validation(targets, validation)

    # ── Save as template ──────────────────────────────────────────────────────
    if meals:
        with st.expander("💾 Save as Template"):
            template_name = st.text_input("Template name", value=f"Daily plan {date.today().isoformat()}")
            if st.button("Save Template", use_container_width=True):
                db.save_diet_template(user_id, template_name, meals)
                st.success("Template saved.")

        templates = db.list_diet_templates(user_id)
        if templates:
            st.subheader("📋 Saved Templates")
            st.dataframe(
                [{"Name": t.get("name"), "Created": str(t.get("created_at", ""))[:10]} for t in templates],
                use_container_width=True,
                hide_index=True,
            )


def log_food_page() -> None:
    _, db, ai, user_id, _ = current_context()
    st.title("📝 Log Food")
    st.caption("Quick buttons first, typing only when needed.")
    show_connection_status()

    meal_type = st.selectbox("Meal", MEAL_TYPES, index=1)

    st.subheader("⚡ Quick Buttons")
    cols = st.columns(len(QUICK_FOODS))
    for col, label in zip(cols, QUICK_FOODS):
        if col.button(label, use_container_width=True):
            with st.spinner(f"Logging {label}..."):
                result = run_async(log_quick_food(db, ai, user_id, meal_type, label))
                st.session_state["last_logged"] = result
                if result["ingredients"]:
                    st.success(f"✅ Logged {label}.")
                else:
                    st.error("Food not found in the database.")

    st.subheader("🕘 Recent Foods")
    recent = get_history(db, user_id)[:6]
    if recent:
        recent_cols = st.columns(3)
        for idx, meal in enumerate(recent):
            label = meal.get("input_text", "Food")
            if recent_cols[idx % 3].button(label, key=f"recent-{meal['id']}", use_container_width=True):
                with st.spinner(f"Logging {label}..."):
                    result = run_async(log_food_text(db, ai, user_id, meal_type, label))
                    st.session_state["last_logged"] = result
                    if result["ingredients"]:
                        st.success(f"✅ Logged {label}.")
                    else:
                        st.error("Food not found in the database.")
    else:
        st.caption("Recent foods appear here after your first log.")

    st.subheader("✏️ Manual Input")
    manual = st.text_input("Food", placeholder="e.g. 100g paneer, 1 bowl rice, 2 eggs")
    if st.button("Log Food", type="primary", use_container_width=True):
        if not manual.strip():
            st.error("Enter a food item first.")
        else:
            with st.spinner("Parsing and logging..."):
                result = run_async(log_food_text(db, ai, user_id, meal_type, manual.strip()))
                st.session_state["last_logged"] = result
                if result["ingredients"]:
                    st.success("✅ Food logged.")
                else:
                    st.error("No valid database foods found.")

    last = st.session_state.get("last_logged")
    if last:
        st.subheader("Last Logged")
        n = last["nutrition"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Calories", f"{n['total_calories']:.0f} kcal")
        c2.metric("Protein", f"{n['total_protein']:.1f} g")
        c3.metric("Fiber", f"{n.get('total_fiber', 0):.1f} g")
        st.json(last["ingredients"], expanded=False)
        for err in last.get("errors", []):
            st.error(err)


def history_page() -> None:
    _, db, _, user_id, _ = current_context()
    st.title("📊 History")
    st.caption("Your meal logs with filters and actions.")
    show_connection_status()

    col1, col2 = st.columns([1, 2])
    selected_date = col1.date_input("Date", value=date.today())
    search = col2.text_input("Search", placeholder="paneer, breakfast")

    meals = get_history(db, user_id, selected_date=selected_date, search=search)
    diets = db.get_diet_history(user_id, selected_date=selected_date)

    if diets:
        st.subheader("📋 Generated Diets")
        st.dataframe(
            [{"Date": d.get("date"), "Calories": d.get("calories"),
              "Protein (g)": d.get("protein"), "Fiber (g)": d.get("fiber")} for d in diets],
            use_container_width=True, hide_index=True,
        )

    if not meals:
        st.info("No food logs found.")
        return

    for meal in meals:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"### {meal.get('meal_type', '').title()}")
            c1.write(meal.get("input_text"))
            c2.metric("Calories", f"{float(meal.get('calories') or 0):.0f}")
            c2.metric("Protein", f"{float(meal.get('protein') or 0):.1f}g")
            c2.metric("Fiber", f"{float(meal.get('fiber') or 0):.1f}g")
            st.caption(str(meal.get("created_at"))[:16])
            u_col, d_col = st.columns(2)
            if u_col.button("Update", key=f"update-{meal['id']}"):
                db.update_meal(user_id, meal["id"], meal["meal_type"], meal["input_text"])
                st.success("Updated")
                st.rerun()
            if d_col.button("🗑 Delete", key=f"delete-{meal['id']}"):
                db.delete_meal(user_id, meal["id"])
                st.success("Deleted")
                st.rerun()


def progress_page() -> None:
    _, db, _, user_id, preferences = current_context()
    st.title("📈 Progress")
    st.caption("Track weight and see the weekly trend.")
    show_connection_status()

    col1, col2 = st.columns(2)
    log_date = col1.date_input("Date", value=date.today())
    default_weight = float(preferences.weight or 70)
    weight = col2.number_input("Weight (kg)", min_value=20.0, max_value=300.0, value=default_weight, step=0.1)
    if st.button("Save Weight", type="primary", use_container_width=True):
        save_weight(db, user_id, weight, log_date)
        st.success("✅ Weight saved.")

    progress = get_progress(db, user_id)
    if not progress:
        st.info("No weight logs yet. Add today's weight above to start the chart.")
        return

    frame = pd.DataFrame(progress)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date")
    st.line_chart(frame.set_index("date")["weight"])
    st.dataframe(frame[["date", "weight"]], use_container_width=True, hide_index=True)


def goals_page() -> None:
    _, db, _, user_id, preferences = current_context()
    st.title("🎯 Goals")
    st.caption(":red[*] = required.  Fiber defaults to 30g if left blank.")
    show_connection_status()
    goals_form_inline(db, user_id, preferences, key_prefix="goals_pg")


def recipe_maker_page() -> None:
    _, db, ai, user_id, preferences = current_context()
    st.title("🍳 Recipe Maker")
    st.caption("Enter ingredients → get nutrition + real recipes instantly.")

    input_text = st.text_area(
        "Ingredients",
        value="100g paneer, 2 eggs, some spinach, little oil",
        height=120,
    )

    if st.button("Give me Recipes", type="primary", use_container_width=True):
        if not input_text.strip():
            st.error("Please enter ingredients first")
            return
            
        with st.spinner("Creating recipes..."):
            goals = db.get_goals(user_id)
            targets = calculate_goal_targets(goals) if goals else {"calories": 2000, "protein": 100, "fiber": 30}
            
            try:
                recipe_result = run_async(
                    ai.generate_independent_recipe(
                        raw_text=input_text,
                        targets=targets,
                        diet_type=preferences.diet_type
                    )
                )
                
                est = recipe_result.nutrition_estimate
                col1, col2, col3 = st.columns(3)
                col1.metric("Est. Calories", f"{est.calories:.0f} kcal")
                col2.metric("Est. Protein", f"{est.protein:.1f} g")
                col3.metric("Est. Fiber", f"{est.fiber:.1f} g")

                st.subheader("Generated Recipes")
                for recipe in recipe_result.recipes:
                    with st.container(border=True):
                        st.subheader(recipe.title)
                        st.caption(f"{recipe.calories:.0f} kcal | {recipe.protein:.1f}g protein | {recipe.prep_time_minutes} min")
                        for idx, step in enumerate(recipe.steps, 1):
                            st.write(f"{idx}. {step}")
            except Exception as e:
                st.error(f"Failed to generate recipes: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar + navigation
# ─────────────────────────────────────────────────────────────────────────────

def sidebar_user_info() -> None:
    _, db, _, user_id, _ = current_context()
    user = db.get_user()
    if user:
        email = getattr(user.user, "email", "")
        st.sidebar.caption(f"👤 {email}")
        if st.sidebar.button("Sign Out", use_container_width=True):
            db.sign_out()
            # Clear all cached session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def main() -> None:
    pages = ["Dashboard", "Generate Diet", "Log Food", "History", "Progress", "Goals", "Recipe Maker"]
    if "page" not in st.session_state:
        st.session_state["page"] = "Dashboard"

    page = st.sidebar.radio(
        "Navigation",
        pages,
        index=pages.index(st.session_state["page"]),
    )

    # Sync manual sidebar navigation with session state
    if page != st.session_state["page"]:
        st.session_state["page"] = page

    sidebar_user_info()

    if page == "Dashboard":
        dashboard_page()
    elif page == "Generate Diet":
        generate_diet_page()
    elif page == "Log Food":
        log_food_page()
    elif page == "History":
        history_page()
    elif page == "Progress":
        progress_page()
    elif page == "Goals":
        goals_page()
    else:
        recipe_maker_page()


if __name__ == "__main__":
    main()
