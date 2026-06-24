# PGY90 Streamlit Cloud Supabase Secrets Guide

R45 prepares a dry run for checking Supabase settings on Streamlit Cloud.
This does not switch the production backend to Supabase.

## Where To Put Secrets

Use Streamlit Cloud Secrets for deployment, or local shell exports for temporary
local tests.

Do not commit real secrets to this repository.
Do not create or commit `.env`.
Do not edit or commit `.streamlit/secrets.toml`.

## Example Streamlit Cloud Secrets

Use the `pgy90-health-coach` Supabase project URL and secret key. Do not reuse
keys from an older PGY90 project.

```toml
SUPABASE_URL = "https://your-project-ref.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"

PGY90_DB_BACKEND = "sqlite"
PGY90_HOME_READ_BACKEND = "sqlite"
PGY90_TREND_READ_BACKEND = "sqlite"
PGY90_WEEKLY_REPORT_READ_BACKEND = "sqlite"
PGY90_WEEKLY_REPORT_WRITE_BACKEND = "sqlite"
PGY90_DAILY_LOG_WRITE_BACKEND = "sqlite"
PGY90_MEAL_LOG_WRITE_BACKEND = "sqlite"
PGY90_LOGIN_USER_LIST_BACKEND = "sqlite"
```

## Safety Notes

- `SUPABASE_SERVICE_ROLE_KEY` is highly sensitive.
- Never write the service role key into `app.py`, docs, README, commits, or UI.
- The service role key is server-side only.
- Do not use the anon key for direct health-data read/write access.
- Keep all backend flags set to `sqlite` until a planned cutover step.
- If a flag is missing, PGY90 defaults to SQLite.

## Local Temporary Test

Use shell exports only for a short test window:

```bash
export SUPABASE_URL="https://your-project-ref.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="temporary-service-role-key"
```

After testing:

```bash
unset SUPABASE_URL
unset SUPABASE_SERVICE_ROLE_KEY
```

Then revoke or rotate the temporary key if one was created for testing.

## Admin Dry Run

In the PGY90 admin area, open:

`管理員後台` -> `Streamlit Cloud / Supabase dry run`

The panel shows:

- whether `SUPABASE_URL` is present
- whether `SUPABASE_SERVICE_ROLE_KEY` is present
- current backend flag values
- read-only counts for selected Supabase tables when secrets are present

The panel never displays the service role key and does not write to Supabase.
