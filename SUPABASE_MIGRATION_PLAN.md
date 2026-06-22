# PGY90 Health Coach SQLite to Supabase Migration Plan

Date: 2026-06-22  
Scope: migration assessment and plan only. No app flow changes, no database writes, no Supabase implementation in this phase.

## 1. SQLite Current State

### Database Path

- SQLite database: `data/health.db`
- Current local file size observed: about 64 KB
- `data/health.db` is not tracked by git and should remain uncommitted.

### Tables

Current SQLite tables:

- `people`
- `app_users`
- `daily_logs`
- `meal_logs`
- `coach_profiles`
- `weekly_reports`
- `coach_profile` legacy table, currently empty
- `sqlite_sequence` SQLite internal table

Current row counts observed in local `data/health.db`:

| Table | Rows |
| --- | ---: |
| `people` | 2 |
| `app_users` | 1 |
| `daily_logs` | 5 |
| `meal_logs` | 14 |
| `coach_profiles` | 1 |
| `coach_profile` | 0 |
| `weekly_reports` | 3 |

Person isolation currently uses `person_name`, not stable `user_id`.

Observed person distribution:

| Table | Person | Rows |
| --- | --- | ---: |
| `daily_logs` | TYP | 5 |
| `meal_logs` | TYP | 14 |
| `weekly_reports` | TYP | 2 |
| `weekly_reports` | 我 | 1 |
| `coach_profiles` | TYP | 1 |
| `people` | TYP | 1 |
| `people` | 我 | 1 |
| `app_users` | TYP | 1 |

### Table Schemas and Purpose

#### `people`

Purpose: list of selectable people / account display names.

Columns:

| Column | Type | Notes |
| --- | --- | --- |
| `person_name` | TEXT | Primary key |
| `created_at` | TEXT | Required |

Migration need: yes. This is the current root identity/person list.

Person isolation: `person_name` is the key.

#### `app_users`

Purpose: login credentials for app users.

Columns:

| Column | Type | Notes |
| --- | --- | --- |
| `person_name` | TEXT | Primary key |
| `password_salt` | TEXT | Required |
| `password_hash` | TEXT | Required |
| `created_at` | TEXT | Required |

Migration need: yes, if keeping the current app-owned auth model during the first Supabase phase.

Person isolation: `person_name` is the key.

Security note: moving to Supabase Auth later may replace this table, but this should not happen in the first migration step unless deliberately planned.

#### `daily_logs`

Purpose: daily health log. Stores body metrics, sleep, BP/pulse, food status, workout, RPE, discomfort, rehab, and notes.

Primary key: `(person_name, log_date)`

Columns:

| Column | Type | Notes |
| --- | --- | --- |
| `person_name` | TEXT | Required, default `我`, primary key part |
| `log_date` | TEXT | Required, primary key part |
| `weight_kg` | REAL | Optional |
| `body_fat_percent` | REAL | Optional |
| `waist_cm` | REAL | Optional |
| `sleep_hours` | REAL | Optional |
| `sleep_quality` | INTEGER | Optional |
| `food_category` | TEXT | Optional |
| `food_notes` | TEXT | Optional |
| `breakfast_category` | TEXT | Optional |
| `breakfast_notes` | TEXT | Optional |
| `lunch_category` | TEXT | Optional |
| `lunch_notes` | TEXT | Optional |
| `dinner_category` | TEXT | Optional |
| `dinner_notes` | TEXT | Optional |
| `snack_notes` | TEXT | Optional |
| `workout_type` | TEXT | Optional |
| `workout_minutes` | INTEGER | Optional |
| `avg_heart_rate` | INTEGER | Optional |
| `max_heart_rate` | INTEGER | Optional |
| `active_calories` | INTEGER | Optional |
| `distance_km` | REAL | Optional |
| `rpe` | INTEGER | Optional |
| `discomfort_notes` | TEXT | Optional |
| `workout_notes` | TEXT | Optional |
| `rehab_done` | INTEGER | Default 0 |
| `rehab_type` | TEXT | Optional |
| `rehab_notes` | TEXT | Optional |
| `notes` | TEXT | Optional |
| `created_at` | TEXT | Required |
| `updated_at` | TEXT | Required |
| `systolic_bp` | INTEGER | Optional |
| `diastolic_bp` | INTEGER | Optional |
| `pulse_bpm` | INTEGER | Optional |

Migration need: yes. This is one of the most important user data tables.

Person isolation: `person_name`.

#### `meal_logs`

Purpose: AI meal records, nutrition estimates, and saved meal entries.

Columns:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER | Primary key autoincrement |
| `log_date` | TEXT | Required |
| `meal_type` | TEXT | Required |
| `description` | TEXT | Required |
| `calories` | INTEGER | Optional |
| `protein_g` | REAL | Optional |
| `fiber_g` | REAL | Optional |
| `carbs_g` | REAL | Optional |
| `fat_g` | REAL | Optional |
| `confidence` | TEXT | Required |
| `created_at` | TEXT | Required |
| `person_name` | TEXT | Required, default `我` |

Migration need: yes. This is core nutrition history.

Person isolation: `person_name`.

#### `coach_profiles`

Purpose: AI coach profile and user nutrition targets.

Columns:

| Column | Type | Notes |
| --- | --- | --- |
| `person_name` | TEXT | Primary key |
| `goal` | TEXT | Required |
| `current_weight_kg` | REAL | Optional |
| `daily_calorie_target` | INTEGER | Optional |
| `protein_target_g` | INTEGER | Optional |
| `fiber_target_g` | INTEGER | Optional |
| `preferences` | TEXT | Optional |
| `updated_at` | TEXT | Required |
| `height_cm` | REAL | Optional |
| `target_weight_kg` | REAL | Optional |
| `target_body_fat_min` | REAL | Optional |
| `target_body_fat_max` | REAL | Optional |
| `gender` | TEXT | Optional |
| `birth_year` | INTEGER | Optional |
| `activity_level` | TEXT | Optional |
| `health_limitations` | TEXT | Optional |

Migration need: yes. This drives personalized nutrition and training advice context.

Person isolation: `person_name`.

#### `weekly_reports`

Purpose: saved weekly health summary text.

Primary key: `(person_name, week_start)`

Columns:

| Column | Type | Notes |
| --- | --- | --- |
| `person_name` | TEXT | Required, default `我`, primary key part |
| `week_start` | TEXT | Required, primary key part |
| `week_end` | TEXT | Required |
| `summary` | TEXT | Required |
| `generated_at` | TEXT | Required |

Migration need: yes, if saved summaries should persist.

Person isolation: `person_name`.

#### `coach_profile`

Purpose: legacy single-profile table from earlier app versions.

Columns:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER | Primary key, CHECK id = 1 |
| `goal` | TEXT | Required |
| `current_weight_kg` | REAL | Optional |
| `daily_calorie_target` | INTEGER | Optional |
| `protein_target_g` | INTEGER | Optional |
| `fiber_target_g` | INTEGER | Optional |
| `preferences` | TEXT | Optional |
| `updated_at` | TEXT | Required |

Migration need: probably no. It is currently empty and superseded by `coach_profiles`.

## 2. Current Data Risk

### Why Streamlit Cloud SQLite loses data

Streamlit Cloud runs the app on an ephemeral filesystem. Files created or modified at runtime, including `data/health.db`, are not durable application storage. When the app restarts, redeploys, is rebuilt, or runs on a different container, the runtime-local SQLite file can disappear or reset to the repository state.

Because `data/health.db` is intentionally not committed to GitHub, the cloud environment does not have a durable copy of production data. This explains why after restart only admin / initial state may remain.

### Why local SQLite is still useful

Local SQLite is still useful for development because:

- It is simple.
- It works without network access.
- It is fast for local testing.
- It avoids touching production data while building features.

But it is not suitable as the formal database for Streamlit Cloud because it is local file storage inside a disposable runtime.

### Highest-priority data to protect

Priority 1:

- `app_users`: login credentials, if current auth remains app-owned.
- `people`: current person identity list.
- `daily_logs`: health, BP, sleep, workout, rehab, notes.
- `meal_logs`: AI meal history and nutrition estimates.
- `coach_profiles`: health goals, preferences, health limitations.

Priority 2:

- `weekly_reports`: saved generated summaries.

Low priority / legacy:

- `coach_profile`: empty legacy table; migrate only if a local source DB has rows.

## 3. Supabase Target Schema Recommendation

Keep the first Supabase schema close to the current SQLite schema. Do not over-redesign yet.

### `profiles` or `people`

Suggested Supabase table: `profiles`

Minimum columns:

- `person_name text primary key`
- `created_at timestamptz not null`

Optional later:

- `user_id uuid`
- `display_name text`
- `role text`

Migration note: keep `person_name` first to reduce app changes.

### `app_users`

Suggested Supabase table: `app_users`

Columns:

- `person_name text primary key references profiles(person_name)`
- `password_salt text not null`
- `password_hash text not null`
- `created_at timestamptz not null`

Migration note: this preserves current login behavior. Later, migrate to Supabase Auth if desired.

### `daily_logs`

Suggested Supabase table: `daily_logs`

Primary key:

- `(person_name, log_date)`

Columns should mirror SQLite:

- `person_name text not null references profiles(person_name)`
- `log_date date not null`
- `weight_kg double precision`
- `body_fat_percent double precision`
- `waist_cm double precision`
- `sleep_hours double precision`
- `sleep_quality integer`
- `food_category text`
- `food_notes text`
- `breakfast_category text`
- `breakfast_notes text`
- `lunch_category text`
- `lunch_notes text`
- `dinner_category text`
- `dinner_notes text`
- `snack_notes text`
- `workout_type text`
- `workout_minutes integer`
- `avg_heart_rate integer`
- `max_heart_rate integer`
- `active_calories integer`
- `distance_km double precision`
- `rpe integer`
- `discomfort_notes text`
- `workout_notes text`
- `rehab_done boolean default false`
- `rehab_type text`
- `rehab_notes text`
- `notes text`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`
- `systolic_bp integer`
- `diastolic_bp integer`
- `pulse_bpm integer`

### `meal_logs`

Suggested Supabase table: `meal_logs`

Columns:

- `id bigint generated by default as identity primary key`
- `person_name text not null references profiles(person_name)`
- `log_date date not null`
- `meal_type text not null`
- `description text not null`
- `calories integer`
- `protein_g double precision`
- `fiber_g double precision`
- `carbs_g double precision`
- `fat_g double precision`
- `confidence text not null`
- `created_at timestamptz not null`

Indexes:

- `(person_name, log_date)`
- `(person_name, log_date, id)`

### `coach_profiles`

Suggested Supabase table: `coach_profiles`

Columns:

- `person_name text primary key references profiles(person_name)`
- `goal text not null`
- `current_weight_kg double precision`
- `daily_calorie_target integer`
- `protein_target_g integer`
- `fiber_target_g integer`
- `preferences text`
- `updated_at timestamptz not null`
- `height_cm double precision`
- `target_weight_kg double precision`
- `target_body_fat_min double precision`
- `target_body_fat_max double precision`
- `gender text`
- `birth_year integer`
- `activity_level text`
- `health_limitations text`

### `weekly_reports`

Suggested Supabase table: `weekly_reports`

Primary key:

- `(person_name, week_start)`

Columns:

- `person_name text not null references profiles(person_name)`
- `week_start date not null`
- `week_end date not null`
- `summary text not null`
- `generated_at timestamptz not null`

### Optional future table naming

The user requested not to over-redesign. For now, keep table names close to SQLite names. Later, if Supabase Auth is introduced, consider:

- `profiles.user_id uuid references auth.users(id)`
- `person_name` becomes display name rather than primary identity.
- Add RLS policies by `user_id`.

## 4. Current SQLite Read/Write Points

### `db.py`

- `DB_PATH = data/health.db`
- `connect()`: creates `data/`, opens SQLite connection, sets `sqlite3.Row`
- `table_columns()`: reads PRAGMA table info

This is the lowest-level access point and the natural place to introduce a DB adapter boundary.

### `meals.py`

Direct SQLite operations:

- `save_meal_log()`: insert into `meal_logs`
- `update_meal_log()`: update `meal_logs`
- `delete_meal_log()`: delete from `meal_logs`
- `load_meals()`: read `meal_logs` by `person_name`

Pure calculation helpers:

- `daily_meal_totals()`
- `coach_feedback()`

### `app.py`

Auth / user / admin:

- `create_account()`
- `set_account_password()`
- `delete_person_data()`
- `user_overview()`
- `account_exists()`
- `registered_usernames()`
- `verify_account()`
- `load_people()`
- `add_person()`
- `person_has_data()`

Schema setup and migrations:

- `init_db()`
- `ensure_family_schema()`

Daily logs:

- `get_daily_log()`
- `upsert_daily_log()`
- `load_logs()`

Coach profile:

- `get_coach_profile()`
- `get_person_height_cm()`
- `get_person_targets()`
- `save_coach_profile()`

Weekly reports:

- `save_weekly_report()`
- `get_saved_report()`

Other functions use loaded dataframes and should not need database-specific changes.

### `ai.py`

No direct SQLite read/write found in this inspection.

## 5. DB Functions to Abstract

Create a DB adapter layer before switching app logic to Supabase.

Recommended adapter interface:

User/account:

- `create_account(person_name, password)`
- `set_account_password(person_name, password)`
- `account_exists(person_name)`
- `registered_usernames()`
- `verify_account(person_name, password)`
- `load_people()`
- `add_person(person_name)`
- `delete_person_data(person_name)`
- `user_overview()`

Daily logs:

- `get_daily_log(person_name, log_date)`
- `upsert_daily_log(values)`
- `load_logs(person_name)`

Meals:

- `save_meal_log(values)`
- `update_meal_log(meal_id, values)`
- `delete_meal_log(meal_id)`
- `load_meals(person_name)`

Coach profile:

- `get_coach_profile(person_name)`
- `save_coach_profile(person_name, values)`
- `get_person_height_cm(person_name)`
- `get_person_targets(person_name)`

Weekly reports:

- `save_weekly_report(person_name, window, summary)`
- `get_saved_report(person_name, window)`

Schema/bootstrap:

- `init_db()` should become SQLite-only.
- Supabase should not run SQLite migrations.
- Add a backend selector later, for example `PGY90_DB_BACKEND=sqlite|supabase`.

## 6. Migration Phases

### Phase 0: Backup and Export

Goal: protect existing local data before any cloud database work.

Steps:

1. Copy `data/health.db` to a timestamped backup outside the repo or under an ignored backup directory.
2. Export SQLite schema:
   - `sqlite3 data/health.db .schema > exports/schema.sql`
3. Export CSV for each important table:
   - `people`
   - `app_users`
   - `daily_logs`
   - `meal_logs`
   - `coach_profiles`
   - `weekly_reports`
4. Record row counts before migration.
5. Do not commit raw production CSV exports if they contain private health data or password hashes.

### Phase 1: Create Supabase Schema

Goal: create cloud tables only. Do not change app code yet.

Steps:

1. Create Supabase project.
2. Add SQL schema matching the current SQLite tables.
3. Keep `person_name` as the primary partition key for the first migration.
4. Add indexes for:
   - `daily_logs(person_name, log_date)`
   - `meal_logs(person_name, log_date)`
   - `weekly_reports(person_name, week_start)`
5. Decide whether RLS is disabled initially for service-role access or enabled with policies.

Recommendation:

- Use service role only from server-side Streamlit secrets.
- Do not expose service role key to browser clients.

### Phase 2: Import Existing SQLite Data

Goal: one-time data import.

Steps:

1. Write `scripts/export_sqlite_to_csv.py` or use SQLite CLI.
2. Write `scripts/import_csv_to_supabase.py` or use Supabase Table Editor / SQL copy.
3. Import order:
   1. `people`
   2. `app_users`
   3. `coach_profiles`
   4. `daily_logs`
   5. `meal_logs`
   6. `weekly_reports`
4. Validate row counts table by table.
5. Spot-check TYP records:
   - latest daily log
   - latest meal log
   - coach profile targets
   - weekly report summaries

### Phase 3: Build DB Adapter

Goal: avoid app-wide Supabase rewrites.

Steps:

1. Move SQLite implementation into `db_sqlite.py` or a `repositories/sqlite_repo.py`.
2. Add a matching Supabase implementation, for example `db_supabase.py`.
3. Keep function signatures similar to current functions.
4. Add a backend selector in `db.py`.
5. Keep `app.py` calling high-level functions, not raw `sqlite3`.

Important:

- Do not convert every feature at once.
- Reduce direct `connect()` usage in `app.py`.
- Move read/write logic to repository functions first.

### Phase 4: Switch Reads and Writes Gradually

Goal: reduce blast radius.

Suggested order:

1. Auth / user basics:
   - `people`
   - `app_users`
   - login verification
2. Coach profiles:
   - `coach_profiles`
3. Daily logs:
   - `daily_logs`
4. Meal logs:
   - `meal_logs`
5. Weekly reports:
   - `weekly_reports`

Each step should have:

- local SQLite test path
- Supabase test path
- row count check
- manual UI smoke test

### Phase 5: Stop Cloud SQLite Writes

Goal: make Supabase the official cloud database.

Steps:

1. Streamlit Cloud uses Supabase through `st.secrets`.
2. Local dev can keep SQLite by default.
3. Add clear environment / secret selector:
   - `PGY90_DB_BACKEND = "supabase"` on Streamlit Cloud
   - `PGY90_DB_BACKEND = "sqlite"` locally
4. Keep `data/health.db` ignored.
5. Add warning if Streamlit Cloud is using SQLite backend.

## 7. Dual Write and One-Click Import Assessment

### One-time import

Recommended first.

Pros:

- Lower risk.
- Easier to validate.
- Keeps app unchanged until schema is ready.

Cons:

- Data written to SQLite after export must be re-imported or synced.

### SQLite / Supabase dual write

Possible, but should not be first unless needed.

Pros:

- Allows gradual confidence while current app still uses SQLite.
- Supabase can be compared against SQLite.

Cons:

- More failure modes.
- Need retry handling.
- Need conflict rules.
- Can create confusing partial writes if Supabase fails after SQLite succeeds.

Recommendation:

1. Do one-time import first.
2. Build adapter.
3. Optional short dual-write test for `daily_logs` and `meal_logs`.
4. Then cut over Streamlit Cloud to Supabase.

## 8. Files Likely Involved Later

Likely modified in actual migration phases:

- `db.py`
  - backend selector
  - common connection/client entry point
- `app.py`
  - remove direct SQLite calls or route them through adapter functions
- `meals.py`
  - move meal CRUD behind adapter
- `requirements.txt`
  - add `supabase` or `postgrest` client package
- `.streamlit/secrets.toml`
  - local secrets only, never commit
- Streamlit Cloud secrets
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY` or safer server-side key strategy
  - `PGY90_DB_BACKEND=supabase`
- New scripts:
  - `scripts/export_sqlite_tables.py`
  - `scripts/import_sqlite_to_supabase.py`
  - `scripts/verify_supabase_counts.py`
- New docs:
  - migration runbook
  - rollback checklist

Probably not modified:

- `ai.py`, unless future AI context reads are moved to adapter functions.

## 9. Things Not To Do

- Do not commit `data/health.db` to GitHub.
- Do not commit CSV exports containing private health data or password hashes.
- Do not directly switch the app to Supabase in this planning phase.
- Do not clear or recreate local SQLite tables.
- Do not destroy local data.
- Do not redesign user identity before data is safe.
- Do not rewrite UI while doing database migration.
- Do not change AI prompts as part of database migration.
- Do not put Supabase service-role secrets in source code.

## 10. Recommended Next Step

Next safest implementation step:

1. Create `exports/` in `.gitignore` if not already ignored.
2. Add a read-only export script that writes schema and CSV files locally.
3. Add a Supabase SQL schema file under `migrations/`.
4. Do not wire app runtime to Supabase yet.

This keeps the migration reversible and protects the current local SQLite data.
