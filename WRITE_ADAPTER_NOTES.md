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
