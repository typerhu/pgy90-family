# Supabase Migration

This folder contains Phase 1 schema planning for PGY90 Health Coach.

## Current Phase

`schema.sql` creates empty Supabase / PostgreSQL tables that mirror the current SQLite schema:

- `people`
- `app_users`
- `daily_logs`
- `meal_logs`
- `coach_profiles`
- `weekly_reports`

The legacy SQLite table `coach_profile` is not created as a formal Supabase table because the current local database has 0 rows there and the app now uses `coach_profiles`.

## Safety Notes

- Do not run data import yet.
- Do not commit real exported CSV files.
- Do not commit database backups.
- Do not put Supabase URL, anon key, service role key, or Streamlit secrets in this repo.
- RLS policies and Supabase Auth integration are intentionally left for later phases.

## Next Phases

- Phase 2: import exported SQLite CSV data into Supabase staging tables or reviewed production tables.
- Phase 3: add a DB adapter layer before changing app reads and writes.
- Phase 4: gradually switch app reads and writes to Supabase.
