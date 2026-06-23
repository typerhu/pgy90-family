# PGY90 Dashboard Backend Pilot Plan

R35 preparation document. This is a read-only dashboard/trend/weekly-report
backend pilot plan. It does not switch any user-facing screen to Supabase.

Current production data source remains SQLite.

## Scope

This phase prepares read-only access models for future display pilots:

- Home `今日狀態總覽`
- Trend charts
- Weekly report views
- Admin display statistics

It does not change:

- Login / logout
- Daily input save
- Meal create / update / delete
- Coach profile save
- Weekly report generation / save
- AI meal coach prompts or meal save flow

## Current Read Requirements

### Home `今日狀態總覽`

Current app path:

- `app.py:home_daily_status_overview()`
- Called from the main page after `load_logs(selected_person)`
- Still reads SQLite through current production helpers

Tables and fields:

| Data | Table | Fields |
| --- | --- | --- |
| Latest body metrics | `daily_logs` | `log_date`, `weight_kg`, `body_fat_percent`, `waist_cm` |
| BMI | `daily_logs` plus profile height | `weight_kg`; `coach_profiles.height_cm` |
| Today sleep | `daily_logs` | `sleep_hours`, `sleep_quality` |
| Today blood pressure / pulse | `daily_logs` | `systolic_bp`, `diastolic_bp`, `pulse_bpm` |
| Training intensity input | `daily_logs`, `coach_profiles` | `sleep_hours`, `sleep_quality`, `systolic_bp`, `diastolic_bp`, `pulse_bpm`, `discomfort_notes`, `workout_minutes`, `rpe`, `health_limitations` |
| Today nutrition progress | `meal_logs`, `coach_profiles` | `log_date`, `calories`, `protein_g`, `fiber_g`, `carbs_g`, `fat_g`, `daily_calorie_target`, `protein_target_g` |

Future read model candidates:

- `get_latest_daily_log(person_name)`
- `get_person_daily_logs(person_name, limit=30)`
- `get_person_meal_logs(person_name, limit=30)`
- `get_latest_meal_entries(person_name, limit=30)`

### Daily Health Record Display

Current app path:

- `daily_input_page(person_name)`
- Reads one day through `get_daily_log(person_name, selected_date)`
- Writes through `upsert_daily_log()` and must not be switched in this phase

Tables and fields:

| Data | Table | Fields |
| --- | --- | --- |
| Selected daily record | `daily_logs` | all daily input fields |
| Health limitations for training card | `coach_profiles` | `health_limitations` |
| Yesterday workout context | `daily_logs` | `workout_minutes`, `rpe` |

Pilot rule:

- Read-only display can be modeled later.
- Save path must remain SQLite until write-path design is complete.

### Body Trend: Weight / Body Fat / Waist / BMI

Current app path:

- `trend_page(df, height_cm)`
- Receives `df = load_logs(selected_person)`

Tables and fields:

| Chart | Table | Fields |
| --- | --- | --- |
| Metric cards | `daily_logs` | `log_date`, `weight_kg`, `body_fat_percent`, `waist_cm` |
| BMI | `daily_logs` plus profile height | `weight_kg`; `coach_profiles.height_cm` |
| Trend line | `daily_logs` | `log_date`, `weight_kg`, `body_fat_percent`, `waist_cm` |

Future read model candidates:

- `get_person_daily_logs(person_name)`
- `get_latest_weight_entries(person_name, limit=30)`

### Sleep Trend

Current app path:

- `trend_page(df, height_cm)`

Tables and fields:

| Chart | Table | Fields |
| --- | --- | --- |
| Sleep bar chart | `daily_logs` | `log_date`, `sleep_hours` |
| Weekly sleep summary | `daily_logs` | `sleep_hours`, `sleep_quality` |

Future read model candidate:

- `get_person_daily_logs(person_name)`

### Blood Pressure / Pulse Trend

Current app path:

- `trend_page(df, height_cm)`

Tables and fields:

| Chart | Table | Fields |
| --- | --- | --- |
| Blood pressure trend | `daily_logs` | `log_date`, `systolic_bp`, `diastolic_bp` |
| Pulse trend | `daily_logs` | `log_date`, `pulse_bpm` |

Important display rules:

- `<= 0` should be treated as missing.
- Do not add diagnosis, classification, or warning logic in backend pilots.

Future read model candidate:

- `get_person_daily_logs(person_name)`

### Nutrition Overview / AI Coach Display

Current app path:

- `coach_page(df, person_name)`
- Reads meal rows through `load_meals(person_name)`
- Computes nutrition totals with `daily_meal_totals(meals, selected_date)`

Tables and fields:

| Data | Table | Fields |
| --- | --- | --- |
| Today meal totals | `meal_logs` | `log_date`, `calories`, `protein_g`, `fiber_g`, `carbs_g`, `fat_g` |
| Meal list | `meal_logs` | `id`, `log_date`, `meal_type`, `description`, nutrition fields, `confidence` |
| Coach targets | `coach_profiles` | `daily_calorie_target`, `protein_target_g`, `fiber_target_g`, `preferences`, `health_limitations` |

Pilot rule:

- Meal reads can be prepared as read-only.
- Meal create/update/delete must not switch until write-path migration is designed.

Future read model candidates:

- `get_person_meal_logs(person_name)`
- `get_latest_meal_entries(person_name, limit=30)`

### Weekly Report Display

Current app path:

- `weekly_report_page(df, person_name)`
- Receives `df = load_logs(selected_person)`
- Reads saved report with `get_saved_report(person_name, window)`
- Writes summary with `save_weekly_report()` when button is pressed

Tables and fields:

| Data | Table | Fields |
| --- | --- | --- |
| Weekly raw data | `daily_logs` | all daily summary fields filtered by `log_date` |
| Saved report | `weekly_reports` | `person_name`, `week_start`, `week_end`, `summary`, `generated_at` |
| Targets | `coach_profiles` | target body composition fields |
| Health limitations | `coach_profiles` | `health_limitations` |

Pilot rule:

- Read-only weekly display can be piloted.
- `save_weekly_report()` must remain SQLite until write migration is designed.

Future read model candidates:

- `get_person_daily_logs(person_name)`
- `get_person_weekly_reports(person_name, limit=3)`

### Admin Dashboard / Statistics

Current app paths:

- `user_overview()`
- `render_db_adapter_status_check()`
- `render_db_sync_status_check()`
- `render_backend_readonly_pilot()`

Tables and fields:

| Data | Table | Fields |
| --- | --- | --- |
| User overview | `people`, `app_users`, `daily_logs`, `meal_logs`, `weekly_reports`, `coach_profiles` | counts by `person_name`, `created_at` |
| Adapter row counts | all core tables | row counts only |
| Sync status | all core tables | key counts and missing/extra counts |
| Read-only backend pilot samples | `people`, `daily_logs`, `meal_logs`, `weekly_reports` | limited non-sensitive fields |

Pilot rule:

- Admin-only display remains the safest backend-switch test surface.

## Read-Only Helper Added in R35

New module:

- `dashboard_read_models.py`

Helpers:

- `get_person_daily_logs(person_name, limit=None, backend=None)`
- `get_person_meal_logs(person_name, limit=None, backend=None)`
- `get_person_weekly_reports(person_name, limit=None, backend=None)`
- `get_latest_daily_log(person_name, backend=None)`
- `get_latest_weight_entries(person_name, limit=30, backend=None)`
- `get_latest_meal_entries(person_name, limit=30, backend=None)`

Backend behavior:

- Default follows `get_db_adapter()`, which defaults to SQLite.
- Passing `backend="sqlite"` reads SQLite.
- Passing `backend="supabase"` reads Supabase if environment variables exist.
- Missing Supabase environment variables should fail clearly in scripts and be
  handled by callers.

Safety rules:

- Read-only only.
- No insert, update, delete, upsert, truncate, or schema migration.
- No password hashes or secrets are displayed by the test script.
- Not wired into formal user-facing UI.

## Test Script Added in R35

New script:

- `scripts/test_dashboard_read_models.py`

What it checks:

- SQLite latest daily log for `TYP`
- SQLite recent daily logs
- SQLite recent meal logs
- SQLite recent weekly reports
- SQLite recent weight entries
- SQLite latest meal entries
- Supabase read if `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` exist
- Supabase skipped cleanly if keys are missing

Commands:

```bash
python3 scripts/test_dashboard_read_models.py
```

Optional Supabase test:

```bash
export SUPABASE_URL="https://xxxxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="xxxxx"
python3 scripts/test_dashboard_read_models.py
```

Do not commit keys, `.env`, `.streamlit/secrets.toml`, `data/`, `exports/`, or
`backups/`.

## Future Pilot Sequence

Recommended next safe sequence:

1. Keep R35 helpers out of formal UI.
2. Use admin-only debug to compare helper output between SQLite and Supabase.
3. Pilot a single display-only dashboard widget behind an explicit feature flag.
4. Add SQLite fallback for every Supabase read.
5. Only after read parity is stable, design write-path migration.

## Non-Goals

- No formal backend switch.
- No app UI change for normal users.
- No write-path changes.
- No Supabase writes.
- No SQLite DB changes.
- No CSV changes.
- No secrets changes.
