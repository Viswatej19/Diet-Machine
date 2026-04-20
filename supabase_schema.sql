create extension if not exists "pgcrypto";

-- ─────────────────────────────
-- FOODS (MASTER TABLE)
-- ─────────────────────────────
create table foods (
  id uuid primary key default gen_random_uuid(),
  name text unique not null,
  calories_per_100g double precision not null,
  protein_per_100g double precision not null default 0,
  carbs_per_100g double precision not null default 0,
  fat_per_100g double precision not null default 0,
  fiber_per_100g double precision not null default 0,
  created_at timestamptz default now()
);

create index foods_lower_name_idx on foods (lower(name));
create index foods_name_prefix_idx on foods (name text_pattern_ops);

-- ─────────────────────────────
-- RECIPES
-- ─────────────────────────────
create table recipes (
  id uuid primary key default gen_random_uuid(),
  name text unique not null,
  ingredients jsonb not null,
  steps text not null,
  nutrition jsonb not null,
  diet_type text default 'any',
  created_at timestamptz default now()
);

-- ─────────────────────────────
-- USER GOALS
-- ─────────────────────────────
create table user_goals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  calories int not null default 2000,
  protein int not null default 100,
  fiber int default 30,
  weight double precision,
  goal text not null default 'maintenance',
  diet_type text not null default 'veg',
  updated_at timestamptz default now()
);

-- ─────────────────────────────
-- MEALS
-- ─────────────────────────────
create table meals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  meal_type text not null,
  input_text text not null,
  ingredients jsonb not null,
  nutrition jsonb not null,
  calories double precision default 0,
  protein double precision default 0,
  fiber double precision default 0,
  created_at timestamptz default now()
);

create index meals_user_created_idx 
on meals (user_id, created_at desc);

-- ─────────────────────────────
-- DAILY DIETS
-- ─────────────────────────────
create table daily_diets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  meal_type text not null,
  items jsonb not null,
  calories double precision default 0,
  protein double precision default 0,
  fiber double precision default 0,
  created_at timestamptz default now()
);

create unique index daily_diets_unique 
on daily_diets (user_id, date, meal_type);

-- ─────────────────────────────
-- DIET HISTORY
-- ─────────────────────────────
create table diet_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  diet_json jsonb not null,
  calories int default 0,
  protein int default 0,
  fiber int default 0,
  created_at timestamptz default now()
);

create unique index diet_history_unique 
on diet_history (user_id, date);

-- ─────────────────────────────
-- FOOD LOGS
-- ─────────────────────────────
create table food_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  food_name text not null,
  calories double precision default 0,
  protein double precision default 0,
  fiber double precision default 0,
  date date not null
);

create index food_logs_user_date_idx 
on food_logs (user_id, date);

-- ─────────────────────────────
-- WEIGHT LOGS
-- ─────────────────────────────
create table weight_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  weight double precision not null,
  created_at timestamptz default now()
);

create unique index weight_logs_unique 
on weight_logs (user_id, date);

-- ─────────────────────────────
-- DIET TEMPLATES
-- ─────────────────────────────
create table diet_templates (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  meals jsonb not null,
  use_daily boolean default false,
  created_at timestamptz default now()
);

-- ─────────────────────────────
-- SEED DATA
-- ─────────────────────────────
insert into foods (name, calories_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, fiber_per_100g)
values
  ('paneer', 265, 18.3, 1.2, 20.8, 0),
  ('eggs', 143, 12.6, 0.7, 9.5, 0),
  ('spinach', 23, 2.9, 3.6, 0.4, 2.2),
  ('oil', 884, 0, 0, 100, 0),
  ('rice', 130, 2.7, 28.2, 0.3, 0.4),
  ('chicken breast', 165, 31, 0, 3.6, 0),
  ('tofu', 144, 17.3, 2.8, 8.7, 2.3),
  ('whey protein', 400, 80, 8, 6, 0),
  ('curd', 98, 11, 3.4, 4.3, 0),
  ('oats', 389, 16.9, 66.3, 6.9, 10.6),
  ('soya chunks', 345, 52, 33, 0.5, 13),
  ('besan', 387, 22.4, 57.8, 6.7, 10.8)
on conflict (name) do nothing;

-- ─────────────────────────────
-- PROFILES & AUTO-CREATE
-- ─────────────────────────────
create table profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz default now()
);

create or replace function handle_new_user()
returns trigger as $$
begin
  insert into profiles (id) values (new.id);
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure handle_new_user();

-- ─────────────────────────────
-- USER PREFERENCES
-- ─────────────────────────────
create table user_preferences (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  calorie_target int not null default 2000,
  protein_target int not null default 100,
  diet_type text not null default 'veg',
  weight double precision,
  goal text not null default 'maintenance',
  created_at timestamptz default now()
);

-- ─────────────────────────────
-- USER LOGS
-- ─────────────────────────────
create table user_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  input_text text not null,
  ingredients jsonb not null,
  nutrition jsonb not null,
  total_calories double precision default 0,
  recipes text,
  created_at timestamptz default now()
);

-- ─────────────────────────────
-- RLS POLICIES (PRODUCTION SAFE)
-- ─────────────────────────────

-- Enable RLS everywhere
alter table profiles enable row level security;
alter table user_preferences enable row level security;
alter table user_logs enable row level security;
alter table foods enable row level security;
alter table recipes enable row level security;
alter table meals enable row level security;
alter table daily_diets enable row level security;
alter table weight_logs enable row level security;
alter table diet_templates enable row level security;
alter table diet_history enable row level security;
alter table user_goals enable row level security;
alter table food_logs enable row level security;

-- Drop existing policies safely
drop policy if exists profiles_own on profiles;
drop policy if exists user_preferences_own on user_preferences;
drop policy if exists user_logs_own on user_logs;
drop policy if exists foods_read on foods;
drop policy if exists recipes_read on recipes;
drop policy if exists meals_own on meals;
drop policy if exists daily_diets_own on daily_diets;
drop policy if exists weight_logs_own on weight_logs;
drop policy if exists diet_templates_own on diet_templates;
drop policy if exists diet_history_own on diet_history;
drop policy if exists user_goals_own on user_goals;
drop policy if exists food_logs_own on food_logs;

-- Create policies (UUID SAFE)
create policy profiles_own on profiles for all using (id = auth.uid());
create policy user_preferences_own on user_preferences for all using (user_id = auth.uid());
create policy user_logs_own on user_logs for all using (user_id = auth.uid());

-- Foods and recipes are globally readable
create policy foods_read on foods for select using (true);
create policy recipes_read on recipes for select using (true);

create policy meals_own on meals for all using (user_id = auth.uid());
create policy daily_diets_own on daily_diets for all using (user_id = auth.uid());
create policy weight_logs_own on weight_logs for all using (user_id = auth.uid());
create policy diet_templates_own on diet_templates for all using (user_id = auth.uid());
create policy diet_history_own on diet_history for all using (user_id = auth.uid());
create policy user_goals_own on user_goals for all using (user_id = auth.uid());
create policy food_logs_own on food_logs for all using (user_id = auth.uid());