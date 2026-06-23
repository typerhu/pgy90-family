"""Read-only dashboard models for future backend pilots.

These helpers prepare dashboard/trend/weekly display reads for the SQLite to
Supabase migration. They are not wired into the Streamlit user-facing UI.
"""

from __future__ import annotations

from typing import Any

from db_adapter import DBAdapter, get_db_adapter


def _adapter(backend: str | None = None) -> DBAdapter:
    return get_db_adapter(backend)


def _sorted_limited_rows(
    rows: list[dict[str, Any]],
    sort_columns: list[str],
    limit: int | None = None,
    descending: bool = True,
) -> list[dict[str, Any]]:
    def sort_key(row: dict[str, Any]) -> tuple[str, ...]:
        return tuple(str(row.get(column) or "") for column in sort_columns)

    sorted_rows = sorted(rows, key=sort_key, reverse=descending)
    if limit is None:
        return sorted_rows
    return sorted_rows[: max(int(limit), 0)]


def _positive_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def get_person_daily_logs(
    person_name: str,
    limit: int | None = None,
    backend: str | None = None,
) -> list[dict[str, Any]]:
    """Return one person's daily logs, newest first."""

    rows = _adapter(backend).get_daily_logs(person_name)
    return _sorted_limited_rows(rows, ["log_date", "created_at"], limit)


def get_person_meal_logs(
    person_name: str,
    limit: int | None = None,
    backend: str | None = None,
) -> list[dict[str, Any]]:
    """Return one person's meal logs, newest first."""

    rows = _adapter(backend).get_meal_logs(person_name)
    return _sorted_limited_rows(rows, ["log_date", "created_at", "id"], limit)


def get_person_weekly_reports(
    person_name: str,
    limit: int | None = None,
    backend: str | None = None,
) -> list[dict[str, Any]]:
    """Return one person's saved weekly reports, newest first."""

    rows = _adapter(backend).get_weekly_reports(person_name)
    return _sorted_limited_rows(rows, ["week_start", "generated_at"], limit)


def get_latest_daily_log(
    person_name: str,
    backend: str | None = None,
) -> dict[str, Any] | None:
    """Return the newest daily log for a person."""

    rows = get_person_daily_logs(person_name, limit=1, backend=backend)
    return rows[0] if rows else None


def get_latest_weight_entries(
    person_name: str,
    limit: int = 30,
    backend: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent daily logs with valid weight values, newest first."""

    rows = get_person_daily_logs(person_name, backend=backend)
    weight_rows = [
        row
        for row in rows
        if _positive_number(row.get("weight_kg")) is not None
    ]
    return weight_rows[: max(int(limit), 0)]


def get_latest_meal_entries(
    person_name: str,
    limit: int = 30,
    backend: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent meal rows for dashboard nutrition displays."""

    return get_person_meal_logs(person_name, limit=limit, backend=backend)
