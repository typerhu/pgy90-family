"""Database adapter draft for the PGY90 SQLite to Supabase migration.

SQLite remains the default and only production backend for the Streamlit app.
This module is not wired into app.py yet; it is a migration preparation layer.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Protocol

from db import DB_PATH


CORE_TABLES = [
    "people",
    "app_users",
    "coach_profiles",
    "daily_logs",
    "meal_logs",
    "weekly_reports",
]


class DBAdapter(Protocol):
    backend_name: str

    def list_people(self) -> list[dict[str, Any]]: ...

    def get_app_users(self, person_name: str | None = None) -> list[dict[str, Any]]: ...

    def get_daily_logs(self, person_name: str | None = None) -> list[dict[str, Any]]: ...

    def get_meal_logs(self, person_name: str | None = None) -> list[dict[str, Any]]: ...

    def get_coach_profiles(self, person_name: str | None = None) -> list[dict[str, Any]]: ...

    def get_weekly_reports(self, person_name: str | None = None) -> list[dict[str, Any]]: ...

    def table_counts(self) -> dict[str, int]: ...


class SQLiteAdapter:
    """Read-only SQLite adapter draft that reuses the existing db.DB_PATH."""

    backend_name = "sqlite"

    def _connect_readonly(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetch_all(
        self,
        table_name: str,
        person_name: str | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = f"SELECT * FROM {table_name}"
        params: list[Any] = []
        if person_name is not None:
            sql += " WHERE person_name = ?"
            params.append(person_name)
        if order_by:
            sql += f" ORDER BY {order_by}"

        with self._connect_readonly() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def _count(self, table_name: str) -> int:
        with self._connect_readonly() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"]) if row else 0

    def list_people(self) -> list[dict[str, Any]]:
        return self._fetch_all("people", order_by="person_name")

    def get_app_users(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all("app_users", person_name, "person_name")

    def get_daily_logs(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all("daily_logs", person_name, "person_name, log_date")

    def get_meal_logs(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all("meal_logs", person_name, "person_name, log_date, created_at")

    def get_coach_profiles(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all("coach_profiles", person_name, "person_name")

    def get_weekly_reports(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._fetch_all("weekly_reports", person_name, "person_name, week_start")

    def table_counts(self) -> dict[str, int]:
        return {table_name: self._count(table_name) for table_name in CORE_TABLES}

    # TODO R29+: add write methods only after app-level call sites are mapped.


class SupabaseAdapter:
    """Read-only Supabase adapter draft.

    This class is intentionally not wired into the app. It only supports read
    methods for migration checks and future adapter design.
    """

    backend_name = "supabase"

    def __init__(
        self,
        supabase_url: str | None = None,
        service_role_key: str | None = None,
    ) -> None:
        self.supabase_url = supabase_url or os.environ.get("SUPABASE_URL")
        self.service_role_key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        missing = []
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.service_role_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if missing:
            names = ", ".join(missing)
            raise RuntimeError(
                f"Missing required environment variable(s): {names}. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to use Supabase."
            )

        try:
            from supabase import create_client
        except ImportError as exc:
            raise RuntimeError("Missing dependency: supabase. Install requirements first.") from exc

        self.client = create_client(self.supabase_url, self.service_role_key)

    def _select(
        self,
        table_name: str,
        person_name: str | None = None,
        order_by: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        query = self.client.table(table_name).select("*")
        if person_name is not None:
            query = query.eq("person_name", person_name)
        for column in order_by or []:
            query = query.order(column)
        response = query.execute()
        return list(getattr(response, "data", None) or [])

    def _count(self, table_name: str) -> int:
        response = self.client.table(table_name).select("*", count="exact").limit(0).execute()
        count = getattr(response, "count", None)
        return int(count) if count is not None else 0

    def list_people(self) -> list[dict[str, Any]]:
        return self._select("people", order_by=["person_name"])

    def get_app_users(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._select("app_users", person_name, ["person_name"])

    def get_daily_logs(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._select("daily_logs", person_name, ["person_name", "log_date"])

    def get_meal_logs(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._select("meal_logs", person_name, ["person_name", "log_date", "created_at"])

    def get_coach_profiles(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._select("coach_profiles", person_name, ["person_name"])

    def get_weekly_reports(self, person_name: str | None = None) -> list[dict[str, Any]]:
        return self._select("weekly_reports", person_name, ["person_name", "week_start"])

    def table_counts(self) -> dict[str, int]:
        return {table_name: self._count(table_name) for table_name in CORE_TABLES}

    # TODO R29+: design write methods after Supabase cutover rules are explicit.


def get_db_backend_name() -> str:
    return os.environ.get("PGY90_DB_BACKEND", "sqlite").strip().lower() or "sqlite"


def get_db_adapter(backend: str | None = None) -> DBAdapter:
    """Return a DB adapter draft.

    The default is always SQLite. Supabase is only selected when explicitly
    requested via argument or PGY90_DB_BACKEND=supabase.
    """

    backend_name = (backend or get_db_backend_name()).strip().lower()
    if backend_name == "sqlite":
        return SQLiteAdapter()
    if backend_name == "supabase":
        return SupabaseAdapter()
    raise ValueError(f"Unsupported PGY90_DB_BACKEND: {backend_name}")
