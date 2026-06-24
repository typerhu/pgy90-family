"""Runtime configuration helpers for env / Streamlit secrets.

Environment variables win over Streamlit secrets. Defaults stay SQLite-first so
adding secrets never changes the app backend unless a flag is explicitly set.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse


SUPABASE_URL_KEY = "SUPABASE_URL"
SUPABASE_SERVICE_ROLE_KEY = "SUPABASE_SERVICE_ROLE_KEY"
BACKEND_FLAG_DEFAULTS = {
    "PGY90_DB_BACKEND": "sqlite",
    "PGY90_HOME_READ_BACKEND": "sqlite",
    "PGY90_TREND_READ_BACKEND": "sqlite",
    "PGY90_WEEKLY_REPORT_READ_BACKEND": "sqlite",
    "PGY90_WEEKLY_REPORT_WRITE_BACKEND": "sqlite",
    "PGY90_DAILY_LOG_WRITE_BACKEND": "sqlite",
    "PGY90_MEAL_LOG_WRITE_BACKEND": "sqlite",
}


def _streamlit_secret_value(key: str) -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get(key, None)
    except Exception:
        return None
    if value is None:
        return None
    return str(value)


def get_config_value(key: str, default: str | None = None) -> str | None:
    env_value = os.environ.get(key)
    if env_value is not None and str(env_value).strip() != "":
        return str(env_value)
    secret_value = _streamlit_secret_value(key)
    if secret_value is not None and secret_value.strip() != "":
        return secret_value
    return default


def get_backend_flag(key: str) -> str:
    default = BACKEND_FLAG_DEFAULTS.get(key, "sqlite")
    return (get_config_value(key, default) or default).strip().lower() or default


def get_supabase_url() -> str | None:
    return get_config_value(SUPABASE_URL_KEY)


def get_supabase_service_role_key() -> str | None:
    return get_config_value(SUPABASE_SERVICE_ROLE_KEY)


def mask_supabase_url(url: str | None) -> str:
    if not url:
        return "missing"
    parsed = urlparse(url)
    host = parsed.netloc or url.replace("https://", "").replace("http://", "")
    if len(host) <= 10:
        masked_host = host
    else:
        masked_host = f"{host[:6]}...{host[-4:]}"
    scheme = parsed.scheme or "https"
    return f"{scheme}://{masked_host}"


def supabase_config_status() -> dict[str, object]:
    url = get_supabase_url()
    key = get_supabase_service_role_key()
    return {
        "supabase_url_present": bool(url),
        "supabase_service_role_key_present": bool(key),
        "masked_supabase_url": mask_supabase_url(url),
        "backend_flags": {
            flag_name: get_backend_flag(flag_name)
            for flag_name in BACKEND_FLAG_DEFAULTS
        },
    }
