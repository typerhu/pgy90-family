# PGY90 Health Coach Supabase Write-Path Design

R39 design document. This document plans future Supabase write migration only.

No Supabase writes are implemented in R39. The production app still writes to
SQLite.

## Current State

- Production write backend: SQLite
- Supabase status: imported, verified, and synced in previous migration phases
- Read-only pilots exist for admin diagnostics, weekly report display, trend
  charts, and home dashboard display
- Formal write paths are not connected to Supabase

## 1. SQLite Write Flow Inventory

### Summary Table

| Feature | Current file / function | Table(s) | Write type | High risk? | Supabase cutover test requirements |
| --- | --- | --- | --- | --- | --- |
| Create account | `app.py:create_account()` | `app_users`, `people` | insert | Yes | New user registration, duplicate person handling, rollback if one table succeeds and the other fails, login after create |
| Reset / set password | `app.py:set_account_password()` | `app_users`, `people` | upsert | Yes | Admin reset flow, existing user login with new password, no password hash leakage, duplicate person handling |
| Delete user data | `app.py:delete_person_data()` | `daily_logs`, `meal_logs`, `weekly_reports`, `coach_profiles`, `app_users`, `people` | delete | Yes | Confirm only selected user data is deleted, no cross-user delete, safe confirmation UI, no accidental cascade surprises |
| Add person | `app.py:add_person()` | `people` | insert ignore | Medium | Idempotent create, no duplicate `person_name`, person selector refresh |
| Daily health save | `app.py:upsert_daily_log()` | `daily_logs` | update / insert | Yes | Insert new date, update same date, duplicate submit, all health fields, local date handling, rollback on failed write |
| Meal create | `meals.py:save_meal_log()` | `meal_logs` | insert | Yes | Text meal save, image meal save, id preservation, nutrition totals update, no duplicate rows on rerun |
| Meal edit | `meals.py:update_meal_log()` | `meal_logs` | update | Yes | Edit selected meal only, preserve person ownership, nutrition totals update |
| Meal delete | `meals.py:delete_meal_log()` | `meal_logs` | delete | Yes | Delete selected row only, no cross-user delete, UI confirmation, daily totals update |
| Coach profile save | `app.py:save_coach_profile()` | `coach_profiles` | upsert | Medium | Save all profile fields, health limitations, activity level, refresh persistence, AI context reads updated values |
| Weekly report save | `app.py:save_weekly_report()` | `weekly_reports` | upsert | Medium | Generate/update same week, saved summary reload, no duplicate weekly row |
| Schema init / migration | `app.py:init_db()`, `app.py:ensure_family_schema()` | all core SQLite tables | schema migration | Yes | Must not run SQLite migration logic against Supabase; Supabase schema must be managed separately |
| Initial import tool | `scripts/import_to_supabase.py` | Supabase core tables | insert | Medium | Empty-table check, validation PASS, counts match, no secrets logged |
| Missing-row sync tool | `scripts/sync_missing_to_supabase.py` | Supabase core tables | insert missing only | Medium | Dry-run first, insert only missing rows, post-sync R29 diff PASS |

### Notes by Flow

#### Create Account

`create_account()` first inserts into `app_users`, then calls `add_person()`.
This is high risk because it spans two tables and directly affects login.
Supabase cutover needs either one server-side transaction-like flow or a clear
rollback / cleanup path if `app_users` succeeds but `people` fails.

#### Password Reset / Set Password

`set_account_password()` upserts `app_users` and then calls `add_person()`.
This stores password salt and hash. It must never expose `password_hash` in UI,
logs, reports, or debug panels. This should not move early.

#### Admin Delete User

`delete_person_data()` deletes from six tables by `person_name`. This is the
highest-risk write path because it is destructive. Do not migrate this until
RLS, ownership, confirmation, and audit behavior are explicit.

#### Daily Health Save

`upsert_daily_log()` checks existence by `person_name + log_date`, then updates
or inserts. Supabase should use the same unique key. The app must avoid duplicate
rows on refresh/rerun and handle partial network failures gracefully.

#### Meal CRUD

`meal_logs` has create, update, and delete paths. This is high risk because meal
rows drive nutrition totals, AI coach context, and today records. Id handling is
important because existing local rows use SQLite integer ids already imported to
Supabase.

#### Coach Profile Save

`save_coach_profile()` upserts by `person_name`. It influences targets, health
limitations, nutrition suggestions, activity-level calculations, and AI context.
It is lower risk than auth or meal CRUD, but still user-visible.

#### Weekly Report Save

`save_weekly_report()` upserts by `person_name + week_start`. This is a good
candidate for the first write pilot because it is a compact table and does not
drive daily data entry or login.

#### Schema Init / Migration

`init_db()` and `ensure_family_schema()` are SQLite-specific runtime schema
helpers. They should not be pointed at Supabase. Supabase schema should stay in
reviewed SQL migrations, not app runtime schema mutation.

## 2. Write Strategy Comparison

### A. Big Bang Cutover

Switch every write path from SQLite to Supabase at once.

Pros:

- Single migration moment.
- No long-term split-brain behavior.
- Simpler final mental model after success.

Cons:

- Large blast radius.
- Hard to isolate failures.
- Auth, daily logs, meals, profile, weekly reports, and admin destructive flows
  all become risky at the same time.
- Rollback becomes difficult if some writes already landed in Supabase.

Risks:

- User cannot log in or save data.
- Meal CRUD may duplicate or lose rows.
- Admin delete/reset mistakes could be severe.
- Streamlit Cloud secret or permission mistakes can break all writes.

Recommendation:

- Not recommended now. The app has too many write paths and health data is too
  important for one large switch.

### B. Dual-Write

Write every change to SQLite and Supabase at the same time.

Pros:

- SQLite remains available while Supabase is tested.
- Can compare data after each write.
- May feel safer during transition.

Cons:

- Hard consistency problem.
- One backend can succeed while the other fails.
- Retry behavior can create duplicates.
- Delete/update ordering is tricky.
- User messages become confusing: did the save succeed or fail?

Risks:

- Split-brain data.
- Partial failure after user refresh/rerun.
- Duplicate meal rows.
- Weekly reports overwritten in one backend but not the other.
- Rollback requires deciding which backend is source of truth.

Recommendation:

- Not recommended as the first write step. It may be useful later for short,
  highly controlled migration windows, but only after idempotency and conflict
  behavior are designed.

### C. Backend Flag Cutover

Use explicit environment flags to move one write path at a time.

Pros:

- Small blast radius.
- Easy to test one feature.
- Easy to turn off by switching env back to SQLite.
- Matches existing R36/R37/R38 read-only pilot pattern.
- Allows per-feature acceptance tests.

Cons:

- More configuration flags.
- Temporary mixed behavior requires clear documentation.
- Each write path still needs dedicated design.

Risks:

- A feature may read from one backend and write to another if flags are poorly
  scoped.
- Fallback behavior must be explicit; automatic fallback after a partial write
  can be dangerous.

Recommendation:

- Recommended strategy, but only in small steps.
- Start with isolated write adapter design and test scripts.
- Do not move login/admin delete/meal CRUD first.

## 3. Recommended Write Cutover Order

### Phase W1: Write Adapter Interface

Goal:

- Define a write adapter interface without wiring it into formal UI.
- Keep SQLite implementation equivalent to current behavior.
- Add Supabase implementation only for isolated tests.

Rules:

- No production write path changes.
- No automatic fallback after partial Supabase writes.
- Every method must define key, conflict behavior, and returned result.

Acceptance:

- Unit/smoke scripts can write to a test-only Supabase table or isolated test
  rows.
- No app UI uses Supabase writes yet.

### Phase W2: Lowest-Risk Write Pilot

Recommended first candidate:

- `weekly_reports` save.

Why weekly report save is safer:

- Table is small.
- Natural unique key: `person_name + week_start`.
- Write frequency is low.
- A failed save does not block daily health logging.
- Saved summary can be regenerated from daily logs.

Alternative:

- `coach_profiles` save.

Why coach profile is slightly riskier:

- It affects nutrition targets, activity level, health limitations, and AI
  context.
- Bad write or stale read can affect daily recommendations.

Recommendation:

- First write pilot should be `weekly_reports`.

### Phase W3: `daily_logs` Write Pilot

Scope:

- Upsert by `person_name + log_date`.
- Covers weight, body fat, waist, blood pressure, sleep, workout, rehab, notes.

Risks:

- Core user data.
- Frequent daily use.
- Duplicate submit / rerun must be handled.

Acceptance:

- Insert new date.
- Update same date.
- Switch date and save.
- Empty/zero optional values behave exactly like SQLite.
- R29 diff remains PASS after test.

### Phase W4: `meal_logs` CRUD Write Pilot

Scope:

- Create meal.
- Edit meal.
- Delete meal.

Risks:

- High frequency.
- AI save flow depends on successful insert.
- Nutrition totals depend on rows.
- Id handling matters.
- Delete is destructive.

Acceptance:

- Text meal save.
- Photo meal save.
- Edit/re-estimate.
- Delete selected meal only.
- No duplicate rows after rerun.
- Nutrition totals match.

### Phase W5: User / Auth / Admin Writes

Scope:

- `people`
- `app_users`
- password reset
- admin delete user

Risks:

- Highest risk.
- Password hashes are sensitive.
- Admin delete is destructive.
- Proper Supabase Auth / RLS policy is not yet integrated.

Recommendation:

- Do not move these until Supabase Auth or an explicit server-side access model
  is designed.

## 4. Table-Level Supabase Write Notes

### `people`

- Key: `person_name`
- Insert: must be idempotent; do not create duplicate people.
- Update: currently minimal; avoid unnecessary updates.
- Delete: only through admin delete flow, after confirmation.
- Fallback / rollback: keep SQLite as source until auth/user cutover is
  explicitly designed.
- Consistency check: compare `people.person_name` sets across SQLite/Supabase.

### `app_users`

- Key: `person_name`
- Insert: stores `password_salt`, `password_hash`, `created_at`.
- Update: password reset updates salt/hash.
- Delete: admin delete only.
- Fallback / rollback: high risk; do not dual-write passwords without strict
  consistency rules.
- Consistency check: compare person names only; never print password hashes.

### `daily_logs`

- Key: `person_name + log_date`
- Insert: new daily record.
- Update: same person/date should update existing row.
- Delete: no normal daily delete flow currently; admin delete removes by person.
- Fallback / rollback: if Supabase write fails before commit, show failure and
  keep current page data unchanged. Do not silently write SQLite after partial
  Supabase success.
- Consistency check: R29 diff on `(person_name, log_date)` plus spot-check key
  numeric fields.

### `meal_logs`

- Key: imported `id` for existing rows; future Supabase id strategy must be
  explicit.
- Insert: new meal row from text/photo estimate.
- Update: edit nutrition fields by `id`.
- Delete: delete by `id`, scoped by person where possible.
- Fallback / rollback: avoid automatic fallback after unknown insert result;
  otherwise duplicate meals are likely.
- Consistency check: compare ids, row counts, and daily nutrition totals.

### `coach_profiles`

- Key: `person_name`
- Insert: first profile save.
- Update: target and preference changes.
- Delete: admin delete only.
- Fallback / rollback: if Supabase fails, keep old profile visible and ask user
  to retry.
- Consistency check: compare profile row count and selected fields such as
  target calories, protein, fiber, activity level, and health limitations
  presence. Do not print full health notes in logs.

### `weekly_reports`

- Key: `person_name + week_start`
- Insert: first saved summary for a week.
- Update: regenerate/update same week.
- Delete: no normal delete flow currently; admin delete removes by person.
- Fallback / rollback: lowest-risk write pilot because summaries can be
  regenerated.
- Consistency check: compare `person_name + week_start`, `week_end`, and
  `generated_at`; optionally compare summary length/hash, not full text in logs.

## 5. Error Handling Design

### Network Failure / Timeout

- User message: "儲存失敗，網路或資料庫暫時無法連線，請稍後再試。"
- Retry: allow manual retry.
- Fallback: do not silently fallback to SQLite after uncertain Supabase write.
- Logging: log table, operation, person/date/key, and sanitized error.
- Duplicate prevention: use unique keys and idempotency where possible.

### Permission Denied / RLS or Grant Denied

- User message: "資料庫權限設定尚未完成，這次未儲存。"
- Retry: no automatic retry until configuration is fixed.
- Fallback: switch env back to SQLite if production is impacted.
- Logging: sanitized permission error without secrets.

### Duplicate Key

- User message: "這筆資料已存在，系統會改用更新流程或請重新整理後再試。"
- Retry: for known upsert paths, use explicit upsert. For meal create, do not
  blindly retry.
- Duplicate prevention: enforce unique keys and check operation type.

### Invalid Payload

- User message: "資料格式不符合要求，請檢查輸入後再儲存。"
- Retry: only after correction.
- Logging: field names, not sensitive values.

### Partial Failure

- User message: "部分資料可能未完成儲存，請先不要重複提交，管理員需要檢查同步狀態。"
- Retry: no automatic retry until key state is known.
- Fallback: manual rollback to SQLite if needed.
- Logging: exact operation step and key.

### User Refresh / Duplicate Submit / Streamlit Rerun

- User message: usually none if idempotent; otherwise show duplicate warning.
- Retry: controlled by form submit state and unique keys.
- Duplicate prevention:
  - Daily logs: upsert by `person_name + log_date`.
  - Weekly reports: upsert by `person_name + week_start`.
  - Meals: avoid reusing stale estimate/session state after successful insert.

## 6. Rollback / Fallback Plan

Before any write cutover:

1. Run R23 backup/export:
   - `python3 scripts/export_sqlite_backup.py`
2. Run R29 diff:
   - `python3 scripts/compare_sqlite_supabase.py`
3. Run R30 sync if needed:
   - `python3 scripts/sync_missing_to_supabase.py --dry-run`
   - `python3 scripts/sync_missing_to_supabase.py`
4. Confirm admin sync panel shows PASS.

If write cutover fails:

1. Immediately switch the write env flag back to SQLite.
2. Keep the local SQLite DB.
3. Do not delete Supabase rows.
4. Do not truncate Supabase tables.
5. Run a diff to understand whether Supabase has rows SQLite does not.
6. If Supabase has new rows not in SQLite, design a one-way recovery sync before
   retrying cutover.
7. Keep logs of the failing operation and affected key.

Important:

- Automatic fallback after a known failed pre-write is acceptable.
- Automatic fallback after an uncertain partial Supabase write is dangerous and
  should be avoided.

## 7. Streamlit Cloud Cutover Notes

Future Supabase write usage on Streamlit Cloud requires:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
PGY90_DB_BACKEND=supabase
```

Existing read pilot flags may also be used:

```text
PGY90_HOME_READ_BACKEND=supabase
PGY90_TREND_READ_BACKEND=supabase
PGY90_WEEKLY_REPORT_READ_BACKEND=supabase
```

Rules:

- Store service role key only in Streamlit Secrets.
- Never commit keys.
- Never place keys in `app.py`, markdown docs, `.env`, or screenshots.
- Never display keys in UI.
- Do not use anon key directly for personal health data.
- Multi-user production use needs RLS policies, Supabase Auth, or another
  explicit server-side access policy.
- Service role is server-side only and should be treated as high-risk.

## 8. Recommended R40+ Tasks

### R40: Write Adapter Interface Draft

Goal:

- Define write method names and payload contracts for SQLite/Supabase adapters.

Risk:

- Low if not wired into UI.

Acceptance:

- Interface exists.
- SQLite behavior can be mapped to current functions.
- Supabase methods can raise `NotImplementedError` or run only in isolated
  scripts.

Do not:

- Wire into app forms.
- Write Supabase production data.

### R41: Supabase Isolated Write Test Script

Goal:

- Create a local script that writes test-only rows to Supabase and cleans them
  only if explicitly designed.

Risk:

- Medium because it writes Supabase.

Acceptance:

- Uses environment variables only.
- Clearly names test rows.
- Does not touch real user data.
- Reports PASS/FAIL without secrets.

Do not:

- Run against production rows.
- Truncate or delete real data.

### R42: Weekly Report Save Write Pilot

Goal:

- Add a narrowly scoped flag for `weekly_reports` save path.

Risk:

- Medium-low.

Acceptance:

- SQLite default remains unchanged.
- Supabase save works for one week.
- Regenerate/update same week works.
- R29 diff remains PASS.

Do not:

- Move daily logs, meals, auth, or admin delete.

### R43: `daily_logs` Write Pilot Design

Goal:

- Design, not implement, daily log Supabase upsert.

Risk:

- Medium-high.

Acceptance:

- Field mapping complete.
- Duplicate submit behavior defined.
- Rollback/fallback behavior defined.

Do not:

- Switch daily input save yet.

### R44: `meal_logs` CRUD Write Pilot Design

Goal:

- Design create/update/delete behavior for meal logs.

Risk:

- High.

Acceptance:

- Id handling documented.
- Duplicate prevention documented.
- Delete safety documented.
- Nutrition total verification documented.

Do not:

- Move meal CRUD before design is approved.

### R45: Streamlit Cloud Supabase Secrets Dry Run

Goal:

- Verify Streamlit Cloud can read Supabase secrets and perform read-only checks.

Risk:

- Low to medium, depending on secret handling.

Acceptance:

- Read-only admin checks work.
- No secrets shown in UI/logs.
- Missing secrets produce safe warnings.

Do not:

- Enable Supabase writes.
- Expose service role key.

## R39 Non-Goals

- No Supabase write implementation.
- No app behavior change.
- No formal backend switch.
- No daily input save change.
- No meal CRUD change.
- No login/admin write change.
- No Supabase schema change.
- No SQLite DB or CSV modification.
- No secrets modification.
