# Diet Maker & Recipe Maker

Streamlit daily-use diet system for planning meals, logging food quickly, tracking progress, and generating recipes with OpenAI and Supabase.

## Features

- Daily dashboard with calories, protein, diet score, quick actions, and correction suggestions.
- One-click daily diet generation for breakfast, lunch, dinner, and snacks.
- Supabase Auth login with email/password and Google fallback to email.
- Required goals for calories and protein, with optional fiber defaulting to 30g.
- Deterministic diet validation for calories, protein, and fiber before saving.
- Quick food logging buttons, recent foods, and manual input fallback.
- Clear meal history table with date/search filters and edit/delete actions.
- Weight tracking with a progress line chart.
- Goal setup from weight and goal type, with automatic calorie/protein targets.
- Save generated daily diets as reusable templates.
- Natural language ingredient parsing with strict OpenAI name normalization only.
- Unit normalization for grams, milliliters, and piece-based foods.
- Nutrition lookup from Supabase only; missing foods are shown as validation errors.
- Local demo fallbacks when API keys are not configured.

## Setup

1. Create and activate a virtual environment.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies.

```powershell
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your keys.

```powershell
Copy-Item .env.example .env
```

4. In Supabase, run `supabase_schema.sql` in the SQL editor. If you already created the v1 schema, run this file again; it uses `if not exists` and adds the v2 columns/tables.

5. Start the app.

```powershell
streamlit run app.py
```

## Environment Variables

- `OPENAI_API_KEY`: Required for real AI parsing, nutrition fallback, and recipe generation.
- `OPENAI_MODEL`: Defaults to `gpt-4o-mini`.
- `SUPABASE_URL`: Supabase project URL.
- `SUPABASE_KEY`: Supabase anon key for local testing, or service key for trusted server-side use.
- `APP_USER_ID`: Stable local user id for preferences.

## Notes

- Supabase writes are skipped if credentials are missing, so the app can be tested locally first.
- OpenAI is never used for nutrition values.
- Database nutrition rows are marked as `Database`; missing foods are never estimated silently.
- Run validation with `python -m pytest -q`.
