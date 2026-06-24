# PGY90 Post-Cutover Safety Check

R47 documents the post-cutover safety routine for PGY90 Health Coach after the
controlled Supabase migration pilots.

## Current Cutover State

The app is intentionally still conservative:

- `PGY90_DB_BACKEND = "sqlite"`
- Login user list can use Supabase fallback.
- Login password verification can use Supabase fallback.
- Home, trend, and weekly report read paths may use Supabase.
- `weekly_reports`, `daily_logs`, and `meal_logs` write pilots may use Supabase
  when their explicit flags are set.

Keeping `PGY90_DB_BACKEND=sqlite` preserves a simple rollback switch while the
read/write pilot flags continue to be observed in production.

## Safety Script

Run the read-only check locally or in a trusted admin environment:

```bash
python3 scripts/post_cutover_safety_check.py
```

Optional JSON output:

```bash
python3 scripts/post_cutover_safety_check.py --json
```

Required environment variables:

```bash
export SUPABASE_URL="https://your-project-ref.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="temporary-service-role-key"
```

The script never prints the key and never writes to Supabase, SQLite, CSV files,
or `exports/`.

## What The Check Reads

Tables:

- `people`
- `app_users`
- `coach_profiles`
- `daily_logs`
- `meal_logs`
- `weekly_reports`

Checks:

- Row counts for all core tables.
- Hard duplicate keys:
  - `daily_logs`: `person_name + log_date`
  - `weekly_reports`: `person_name + week_start`
  - `meal_logs`: `id`
- Possible duplicate meal warning:
  - `person_name + log_date + meal_type + description + calories`
- Recent rows:
  - last 5 `daily_logs`
  - last 5 `meal_logs`
  - last 5 `weekly_reports`
- `person_name` relationship checks against `people.person_name`.
- Current cutover flags from runtime config.

The script does not display `password_hash`, `password_salt`, secrets, or long
weekly report summaries.

## Suggested Daily Checks

During the first days after cutover:

1. Confirm the app can log in as the expected user.
2. Add one daily health record and confirm it appears in Supabase.
3. Add, edit, and delete one test meal; confirm no test row remains.
4. Open Home, Trend, and Weekly Report views.
5. Run:

```bash
python3 scripts/post_cutover_safety_check.py
```

6. Review Supabase table counts in the admin dry run panel.

## Status Meaning

`PASS`:

- Supabase is readable.
- No hard duplicate keys.
- No hard `person_name` relationship errors.
- Key tables have reasonable row counts.

`WARNING`:

- Supabase credentials are missing, so the check is skipped.
- Possible duplicate meal rows need manual review.
- Non-critical fields such as timestamps need review.
- Cloud SQLite and Supabase counts differ after cutover; this can be expected
  because Supabase is now the active data store for pilot paths.

`FAIL`:

- Supabase cannot be read when credentials are present.
- Duplicate hard keys exist.
- `person_name` references are broken.
- `people` or `app_users` are unexpectedly empty after cutover.

## Rollback Plan

If production behavior becomes unsafe:

1. Set pilot flags back to `sqlite`.
2. Keep `PGY90_DB_BACKEND=sqlite`.
3. Do not truncate Supabase.
4. Do not delete production Supabase rows.
5. Run the safety check and compare recent writes.
6. If Supabase has newer data that SQLite does not have, plan a careful
   one-way recovery script instead of deleting data.
7. Keep service role keys only in Streamlit Cloud Secrets or local shell exports.

## When To Consider The Next Phase

Only consider `PGY90_DB_BACKEND=supabase` or removing SQLite fallbacks after:

- Login works reliably for the expected users.
- Home, trend, and weekly report reads are stable for several days.
- `daily_logs`, `meal_logs`, and `weekly_reports` writes are stable.
- The post-cutover safety check is clean or has only understood warnings.
- A rollback path remains documented and tested.

## Do Not Do Yet

- Do not truncate Supabase.
- Do not delete production Supabase data.
- Do not remove SQLite fallback immediately.
- Do not expose service role keys in the UI or logs.
- Do not commit `.streamlit/secrets.toml`.
- Do not commit `data/`, `exports/`, or `backups/`.
