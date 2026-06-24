# PGY90 Write Adapter Notes

R40 creates a write adapter interface and dry-run skeleton only.

## What R40 Adds

- `write_adapter.py`
- `scripts/test_write_adapter.py`

The write adapter defines future write-path methods:

- `save_weekly_report(...)`
- `upsert_daily_log(...)`
- `save_meal_log(...)`
- `update_meal_log(...)`
- `delete_meal_log(...)`
- `save_coach_profile(...)`

## Safety Boundaries

- Not wired into the Streamlit app.
- Not used by daily input.
- Not used by meal CRUD.
- Not used by login, admin reset, or admin delete.
- Does not write to Supabase.
- Does not modify production `data/health.db`.
- Does not modify CSV exports.
- Does not read or print secrets.

## Current Behavior

Both `SQLiteWriteAdapter` and `SupabaseWriteAdapter` are dry-run skeletons.
They validate payloads and return `WriteResult` objects that describe what would
be written later.

`PGY90_WRITE_BACKEND` is reserved for future isolated tests, but formal app
writes do not use it.

## Recommended First Future Pilot

The first real write pilot should still be `weekly_reports` save because:

- It has a clear unique key: `person_name + week_start`.
- It is low-frequency.
- It does not affect daily logging or meal records.
- It can be regenerated from daily logs if needed.

Do not move `meal_logs` CRUD, user auth, admin reset, or admin delete before
dedicated write-path design and tests.

## R41 Isolated Supabase Weekly Report Write Test

R41 adds `scripts/test_supabase_weekly_report_write.py` as a standalone script.
It is not imported by the Streamlit app and does not change formal app writes.

The script validates a `weekly_reports` payload in dry-run mode by default:

```bash
python3 scripts/test_supabase_weekly_report_write.py --dry-run
```

The only mode that can write to Supabase is explicit execute mode:

```bash
python3 scripts/test_supabase_weekly_report_write.py --execute
```

Execute mode uses the test-only key `__R41_TEST__ | 2099-01-01`, then attempts
insert, read back, update, cleanup, and cleanup verification. It must not write
real `person_name` report data, and it must not touch SQLite.

## R42 Weekly Reports Save Pilot

R42 enables one narrow app write pilot for `weekly_reports` only.

- Default behavior remains SQLite.
- `PGY90_WEEKLY_REPORT_WRITE_BACKEND=sqlite` keeps the original SQLite save path.
- `PGY90_WEEKLY_REPORT_WRITE_BACKEND=supabase` first saves to SQLite, then attempts
  a Supabase `weekly_reports` upsert by `person_name + week_start`.
- Supabase failures are shown as warnings and do not block the SQLite save.
- No other write paths use the Supabase write adapter.

The following remain out of scope:

- `daily_logs` writes
- `meal_logs` CRUD
- `coach_profiles` writes
- auth / admin writes

## R43 Daily Logs Save Pilot

R43 enables one additional app write pilot for `daily_logs` only.

- Default behavior remains SQLite.
- `PGY90_DAILY_LOG_WRITE_BACKEND=sqlite` keeps the original SQLite save path.
- `PGY90_DAILY_LOG_WRITE_BACKEND=supabase` first saves to SQLite, then reads back
  the saved row and attempts a Supabase `daily_logs` upsert by
  `person_name + log_date`.
- Supabase failures are shown as warnings and do not block the SQLite save.
- No meal, auth, coach profile, or admin write path uses the Supabase write
  adapter.

The Supabase daily log payload is restricted to known `daily_logs` columns and
converts `rehab_done` to a boolean-compatible value.

## R44 Meal Logs CRUD Pilot

R44 enables one additional app write pilot for `meal_logs` CRUD only.

- Default behavior remains SQLite.
- `PGY90_MEAL_LOG_WRITE_BACKEND=sqlite` keeps the original SQLite save, update,
  and delete paths.
- `PGY90_MEAL_LOG_WRITE_BACKEND=supabase` keeps SQLite as the baseline, then
  attempts the matching Supabase operation after SQLite succeeds.
- Meal insert and update use the SQLite `meal_logs.id` as the Supabase row key.
- Meal delete deletes only the matching Supabase `id`, scoped by `person_name`
  when the local row is available before deletion.
- Supabase failures are shown as warnings and do not roll back the SQLite result.

The following remain out of scope:

- `coach_profiles` writes
- auth / admin writes
- Supabase schema changes

### R44 Unicode Fix

Meal log Supabase writes use the REST endpoint with explicit UTF-8 JSON body
serialization. The request body is encoded with `ensure_ascii=False` and
`utf-8`, while row targeting uses ASCII-safe `id` filters only. Chinese
`meal_type` and `description` values stay in the JSON body and are not placed in
headers or filter query values.
