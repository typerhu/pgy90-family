# PGY90 Health Coach Supabase Cutover Readiness

R33 checklist. This document is a pre-cutover risk review only.

Current production app behavior remains SQLite-first. This report does not switch
the app backend, change write flows, modify Supabase, or modify `data/health.db`.

## Current Snapshot

- Current app backend: SQLite
- Current SQLite database: `data/health.db`
- Supabase migration status: imported and read-verified in earlier phases
- Latest known SQLite / Supabase sync state:
  - `people`: 2 / 2
  - `app_users`: 1 / 1
  - `coach_profiles`: 1 / 1
  - `daily_logs`: 6 / 6
  - `meal_logs`: 15 / 15
  - `weekly_reports`: 3 / 3

Supabase is ready for controlled read-only pilots, but not ready to become the
default backend until write-path behavior, rollback rules, and secrets handling
are explicitly tested.

## 1. Direct SQLite Usage Inventory

### Formal App Main Flow

These are still part of the live Streamlit app behavior and must not be switched
casually.

| File | SQLite usage | Current role |
| --- | --- | --- |
| `db.py` | `DB_PATH`, `connect()` using `sqlite3.connect(DB_PATH)` | Central SQLite connection helper |
| `app.py` | imports `DB_PATH`, `DATA_DIR`, `connect`, `table_columns` | Main app reads, writes, schema init, migrations, auth, daily logs, profiles, reports |
| `meals.py` | imports `connect()` | Meal create, update, delete, and meal list reads |

Important app functions still using SQLite directly:

| Function | File | Table(s) | Type |
| --- | --- | --- | --- |
| `create_account()` | `app.py` | `app_users`, `people` | write |
| `set_account_password()` | `app.py` | `app_users`, `people` | write |
| `delete_person_data()` | `app.py` | `daily_logs`, `meal_logs`, `weekly_reports`, `coach_profiles`, `app_users`, `people` | destructive write |
| `user_overview()` | `app.py` | multiple core tables | read |
| `account_exists()` | `app.py` | `app_users` | read |
| `registered_usernames()` | `app.py` | `app_users` | read |
| `verify_account()` | `app.py` | `app_users` | read |
| `ensure_family_schema()` | `app.py` | multiple core tables | schema migration |
| `init_db()` | `app.py` | multiple core tables | schema init / migration |
| `load_people()` | `app.py` | `people` | read |
| `add_person()` | `app.py` | `people` | write |
| `person_has_data()` | `app.py` | `daily_logs`, `meal_logs`, `weekly_reports`, `coach_profiles` | read |
| `get_daily_log()` | `app.py` | `daily_logs` | read |
| `upsert_daily_log()` | `app.py` | `daily_logs` | write |
| `load_logs()` | `app.py` | `daily_logs` | read |
| `get_coach_profile()` | `app.py` | `coach_profiles` | read |
| `save_coach_profile()` | `app.py` | `coach_profiles` | write |
| `save_weekly_report()` | `app.py` | `weekly_reports` | write |
| `get_saved_report()` | `app.py` | `weekly_reports` | read |
| `save_meal_log()` | `meals.py` | `meal_logs` | write |
| `update_meal_log()` | `meals.py` | `meal_logs` | write |
| `delete_meal_log()` | `meals.py` | `meal_logs` | destructive write |
| `load_meals()` | `meals.py` | `meal_logs` | read |

### Adapter / Admin Debug Layer

These are read-only migration helpers or admin-only diagnostics. They are safer
than production flows but still require Supabase secrets when reading Supabase.

| File | Usage | Current role |
| --- | --- | --- |
| `db_adapter.py` | imports `DB_PATH`; `SQLiteAdapter` opens SQLite in read-only mode; `SupabaseAdapter` reads Supabase | Migration adapter draft, not app backend |
| `db_sync_status.py` | uses `SQLiteAdapter` and `SupabaseAdapter` | Admin-only SQLite / Supabase sync status helper |
| `scripts/test_db_adapter.py` | uses adapter | Read-only smoke test |
| `scripts/compare_sqlite_supabase.py` | reads SQLite and Supabase | Read-only diff report |

### Migration / Export Tools

These are local tools, not app runtime. They should remain separate from the app
main flow.

| File | Usage | Current role |
| --- | --- | --- |
| `scripts/export_sqlite_backup.py` | direct `DB_PATH`; read-only SQLite connection; copies DB backup | Phase 0 backup/export |
| `scripts/validate_supabase_import.py` | reads exported CSV and schema | Import validation only |
| `scripts/import_to_supabase.py` | reads CSV, inserts into Supabase | One-time import tool |
| `scripts/verify_supabase_read.py` | reads Supabase | Read verification |
| `scripts/sync_missing_to_supabase.py` | reads SQLite/Supabase and inserts missing rows | Controlled missing-row sync |

## 2. Feature Risk Classification

### A. Good Candidates for Read-Only Pilot

These can use the adapter first because they do not change user data.

- Admin database status check
- Admin SQLite / Supabase sync status panel
- Admin-only row count and diff display
- Dashboard display-only summaries
- Weekly report display-only views
- Trend data display-only pilot, after dashboard is proven stable

### B. Requires Cautious Read-Only Cutover

These are visible user-facing areas. They are reads, but mistakes would confuse
the user or make data appear missing.

- Home `今日狀態總覽`
- Trend charts
- Weekly report view
- AI coach display sections that read today's meals and targets
- Today's nutrition overview reads

Cut these over behind a backend flag with SQLite fallback.

### C. Do Not Switch in the First Batch

These are write-heavy, auth-sensitive, destructive, or user trust critical.

- Login / logout / remember-me behavior
- Account creation and password changes
- Daily input save
- Meal add / edit / delete / re-estimate save
- Coach profile edit and save
- Weekly report generation and save
- Admin reset password
- Admin delete user
- Schema init / migration

These need explicit design, transaction behavior, error handling, rollback
planning, and post-write verification before any backend switch.

## 3. SQLite Write Flow Inventory

| Feature | File / function | Writes table(s) | Difficulty | Cutover tests required |
| --- | --- | --- | --- | --- |
| Create user account | `app.py:create_account()` | `app_users`, `people` | High | New user registration, duplicate user handling, login after create, rollback on partial failure |
| Reset / set password | `app.py:set_account_password()` | `app_users`, `people` | High | Admin reset, existing user password update, login with new password, no secret leakage |
| Delete user data | `app.py:delete_person_data()` | `daily_logs`, `meal_logs`, `weekly_reports`, `coach_profiles`, `app_users`, `people` | High | Confirm only selected user deleted, no cross-user delete, cancellation path, audit before destructive action |
| Add person | `app.py:add_person()` | `people` | Medium | Idempotent insert, duplicate person handling, person selector refresh |
| Daily input save | `app.py:upsert_daily_log()` | `daily_logs` | High | Insert new day, update same day, date handling, blood pressure fields, sleep, workout, rehab, notes |
| Meal create | `meals.py:save_meal_log()` | `meal_logs` | High | Text meal save, image meal save, nutrition totals update, person isolation |
| Meal update | `meals.py:update_meal_log()` | `meal_logs` | High | Edit saved meal, recalculate daily totals, preserve meal id/person |
| Meal delete | `meals.py:delete_meal_log()` | `meal_logs` | High | Delete selected meal only, daily totals update, no cross-user delete |
| Coach profile save | `app.py:save_coach_profile()` | `coach_profiles` | Medium / High | Upsert profile, health limitations, activity level, personal AI context, refresh/login persistence |
| Weekly report save | `app.py:save_weekly_report()` | `weekly_reports` | Medium | Generate/update same week, preserve week boundaries, saved summary reload |
| Schema init and migration | `app.py:init_db()`, `app.py:ensure_family_schema()` | multiple tables and schema | High | Separate Supabase migrations from runtime, no destructive live migration, idempotent SQL |
| Supabase missing-row sync tool | `scripts/sync_missing_to_supabase.py` | Supabase core tables | Medium | Dry-run first, insert missing only, no update/delete/truncate, post-sync diff PASS |
| Initial Supabase import tool | `scripts/import_to_supabase.py` | Supabase core tables | Medium | Empty target check, validation PASS, post-import counts match |

Login verification (`verify_account()`), user lists, reports, trends, and meal
loads are read paths, but they are tightly coupled to write correctness and user
trust. They should move only after adapter read pilots are stable.

## 4. Supabase Secrets / Environment Requirements

Future Supabase-backed app runs need:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
PGY90_DB_BACKEND=supabase
```

Rules:

- Do not commit these values.
- Do not write them into `app.py`.
- Do not write real values into README or docs.
- Do not store them in `SUPABASE_CUTOVER_READINESS.md`.
- Streamlit Cloud should store them in Secrets.
- Local testing can use shell `export`.
- `SUPABASE_SERVICE_ROLE_KEY` is high-risk and must be server-side only.
- Never expose the service role key to browser JavaScript or client-side code.
- Do not print secrets to terminal, logs, reports, or UI.

## 5. RLS / Grants Status

Current migration understanding:

- Supabase tables have RLS enabled.
- `service_role` has grants for `select`, `insert`, `update`, and `delete`.
- The app is not integrated with Supabase Auth.
- The current app should not use an anon key to directly read/write personal
  health data.
- A future multi-user production setup needs explicit RLS policies before
  broader use.
- Until Supabase Auth and RLS policies are designed, app-side Supabase access
  should remain server-side and carefully scoped.

No Supabase SQL changes are part of R33.

## 6. Phased Cutover Recommendation

### Phase A: Read-Only Admin Validation

Keep the current R31/R32 behavior.

- Admin can inspect DB backend row counts.
- Admin can inspect SQLite / Supabase sync status.
- No user-facing data source changes.
- No writes.

Acceptance criteria:

- App works without Supabase secrets.
- With Supabase secrets, admin-only counts and sync status load.
- Missing secrets never crash the app.

### Phase B: Read-Only Display Pilot

Switch exactly one low-risk display area to the adapter behind an explicit flag.

- Use `PGY90_DB_BACKEND=supabase` only for the pilot area.
- Keep SQLite fallback.
- Do not switch writes.
- Do not switch auth.

Good first target:

- Admin dashboard display / row count style data.

Acceptance criteria:

- SQLite and Supabase render the same result.
- Fallback to SQLite works if Supabase read fails.
- General user flows remain unchanged.

### Phase C: Read-Only Dashboard Pilot

Move selected display-only user areas gradually.

Candidate order:

1. Home `今日狀態總覽`
2. Trend chart read queries
3. Weekly report view read queries
4. AI coach read-only context reads

Acceptance criteria:

- Same person isolation.
- Same date handling using local Malaysia timezone logic.
- Same counts and values as SQLite.
- No writes through Supabase yet.

### Phase D: Write-Path Design and Dual Check

Design before implementing.

- Define transaction expectations for each write path.
- Define error messages and retry behavior.
- Define post-write verification checks.
- Avoid automatic dual-write as a first production strategy unless rollback and
  duplicate prevention are fully specified.
- Decide how to handle id preservation for `meal_logs`.
- Decide how to handle destructive admin actions.

Acceptance criteria:

- Written design reviewed.
- Each write path has a test matrix.
- Rollback plan is documented.

### Phase E: Primary Backend Cutover

Supabase becomes the primary backend only after read pilots and write design are
stable.

- Streamlit Cloud secrets configured.
- `PGY90_DB_BACKEND=supabase` enabled.
- SQLite remains local backup / fallback.
- Pre-cutover export, diff, and missing-row sync completed.
- Post-cutover logs monitored.

Acceptance criteria:

- Login, daily saves, meal CRUD, coach profile saves, and weekly report saves
  all pass production-like testing.
- Fallback to SQLite is available.
- No data loss during cutover window.

## 7. Fallback / Rollback Plan

If Supabase cutover fails:

1. Set `PGY90_DB_BACKEND=sqlite`.
2. Keep the SQLite DB available until Supabase is fully proven.
3. Before cutover, run R23 export:
   - `python3 scripts/export_sqlite_backup.py`
4. Before cutover, run R29 diff:
   - `python3 scripts/compare_sqlite_supabase.py`
5. Before cutover, run R30 sync if needed:
   - `python3 scripts/sync_missing_to_supabase.py --dry-run`
   - `python3 scripts/sync_missing_to_supabase.py`
6. After cutover, monitor app logs and Streamlit Cloud errors.
7. If any write path fails or data appears inconsistent, immediately return to
   SQLite backend.
8. Re-run diff and inspect Supabase rows before retrying.

## 8. Recommended Next Tasks

### R34: Read-Only Backend Switch for Admin Dashboard Only

Goal:

- Let one admin-only display area choose SQLite or Supabase through the adapter.
- No user-facing data source switch.
- No writes.

Risk:

- Low.

Acceptance criteria:

- SQLite default works.
- Supabase optional read works with secrets.
- Missing secrets do not crash the app.
- No app write path changes.

### R35: Read-Only Backend Switch for Trend Data Pilot

Goal:

- Pilot adapter reads for trend chart data.
- Keep SQLite fallback.
- No write path changes.

Risk:

- Medium, because trend charts are user-facing and date-sensitive.

Acceptance criteria:

- SQLite and Supabase charts match for the same person/date range.
- 0 and empty values are handled the same way.
- Person isolation is preserved.

### R36: Read-Only Backend Switch for Weekly Report View

Goal:

- Pilot adapter reads for saved weekly report view and weekly raw data display.
- Keep report generation and save on SQLite.

Risk:

- Medium.

Acceptance criteria:

- Saved reports match.
- Weekly date windows match.
- Summary sections remain unchanged.
- No report save path changes.

### R37: Write-Path Design Document

Goal:

- Plan Supabase write behavior before implementing writes.

Risk:

- Documentation task is low risk; resulting write migration is high risk.

Acceptance criteria:

- Every write path has a mapped table, key, conflict behavior, validation plan,
  rollback plan, and test steps.
- No code switch until the design is approved.

## 9. Cutover Gate Checklist

Do not enable Supabase as the primary backend until all of these are true:

- R23 backup/export completed immediately before cutover.
- R29 SQLite / Supabase diff is `PASS`.
- R30 missing-row sync has no pending missing rows.
- Supabase secrets are configured in Streamlit Cloud.
- No secrets are committed to Git.
- Admin status panels work with Supabase secrets.
- At least one read-only user-facing pilot has passed.
- Write-path design exists and has been tested locally.
- Rollback to SQLite has been tested.
- `data/health.db`, `backups/`, and `exports/` remain ignored and uncommitted.

## Non-Goals for R33

- No app backend switch.
- No Supabase writes.
- No SQLite writes.
- No schema changes.
- No RLS or grant changes.
- No app UI changes.
- No login, AI, daily input, trends, or weekly report behavior changes.
