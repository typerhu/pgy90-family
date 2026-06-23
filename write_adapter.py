"""Write adapter skeleton for future PGY90 Supabase cutover.

This module is intentionally not wired into the Streamlit app. It does not
write to production SQLite or Supabase. R40 only defines the interface,
validation, and dry-run payload behavior for future write-path pilots.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


WRITE_BACKEND_ENV = "PGY90_WRITE_BACKEND"
SUPPORTED_WRITE_BACKENDS = {"sqlite", "supabase"}


@dataclass(frozen=True)
class WriteResult:
    backend: str
    operation: str
    table: str
    key: dict[str, Any]
    payload: dict[str, Any]
    dry_run: bool = True
    would_write: bool = False
    message: str = ""


class WriteAdapter(Protocol):
    backend_name: str

    def save_weekly_report(
        self,
        person_name: str,
        week_start: str,
        week_end: str,
        summary: str,
        generated_at: str | None = None,
    ) -> WriteResult: ...

    def upsert_daily_log(self, values: dict[str, Any]) -> WriteResult: ...

    def save_meal_log(self, values: dict[str, Any]) -> WriteResult: ...

    def update_meal_log(self, meal_id: int, values: dict[str, Any]) -> WriteResult: ...

    def delete_meal_log(self, meal_id: int, person_name: str | None = None) -> WriteResult: ...

    def save_coach_profile(self, person_name: str, values: dict[str, Any]) -> WriteResult: ...


def _required_text(value: Any, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required.")
    return cleaned


def build_weekly_report_payload(
    person_name: str,
    week_start: str,
    week_end: str,
    summary: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "person_name": _required_text(person_name, "person_name"),
        "week_start": _required_text(week_start, "week_start"),
        "week_end": _required_text(week_end, "week_end"),
        "summary": _required_text(summary, "summary"),
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
    }


class DryRunWriteAdapter:
    backend_name = "dry-run"

    def _result(
        self,
        operation: str,
        table: str,
        key: dict[str, Any],
        payload: dict[str, Any] | None = None,
        message: str = "",
    ) -> WriteResult:
        return WriteResult(
            backend=self.backend_name,
            operation=operation,
            table=table,
            key=key,
            payload=payload or {},
            dry_run=True,
            would_write=True,
            message=message or "Validated only. No data was written.",
        )

    def save_weekly_report(
        self,
        person_name: str,
        week_start: str,
        week_end: str,
        summary: str,
        generated_at: str | None = None,
    ) -> WriteResult:
        payload = build_weekly_report_payload(
            person_name=person_name,
            week_start=week_start,
            week_end=week_end,
            summary=summary,
            generated_at=generated_at,
        )
        return self._result(
            operation="save_weekly_report",
            table="weekly_reports",
            key={"person_name": payload["person_name"], "week_start": payload["week_start"]},
            payload=payload,
        )

    def upsert_daily_log(self, values: dict[str, Any]) -> WriteResult:
        person_name = _required_text(values.get("person_name"), "person_name")
        log_date = _required_text(values.get("log_date"), "log_date")
        return self._result(
            operation="upsert_daily_log",
            table="daily_logs",
            key={"person_name": person_name, "log_date": log_date},
            payload=dict(values),
            message="Skeleton only. Future implementation must define upsert semantics.",
        )

    def save_meal_log(self, values: dict[str, Any]) -> WriteResult:
        person_name = _required_text(values.get("person_name"), "person_name")
        log_date = _required_text(values.get("log_date"), "log_date")
        return self._result(
            operation="save_meal_log",
            table="meal_logs",
            key={"person_name": person_name, "log_date": log_date},
            payload=dict(values),
            message="Skeleton only. Future implementation must define id handling.",
        )

    def update_meal_log(self, meal_id: int, values: dict[str, Any]) -> WriteResult:
        if int(meal_id) <= 0:
            raise ValueError("meal_id must be positive.")
        return self._result(
            operation="update_meal_log",
            table="meal_logs",
            key={"id": int(meal_id)},
            payload=dict(values),
            message="Skeleton only. Future implementation must scope update by person.",
        )

    def delete_meal_log(self, meal_id: int, person_name: str | None = None) -> WriteResult:
        if int(meal_id) <= 0:
            raise ValueError("meal_id must be positive.")
        key: dict[str, Any] = {"id": int(meal_id)}
        if person_name:
            key["person_name"] = person_name
        return self._result(
            operation="delete_meal_log",
            table="meal_logs",
            key=key,
            message="Skeleton only. Future implementation must confirm delete safety.",
        )

    def save_coach_profile(self, person_name: str, values: dict[str, Any]) -> WriteResult:
        cleaned_person = _required_text(person_name, "person_name")
        return self._result(
            operation="save_coach_profile",
            table="coach_profiles",
            key={"person_name": cleaned_person},
            payload={**values, "person_name": cleaned_person},
            message="Skeleton only. Future implementation must define profile upsert behavior.",
        )


class SQLiteWriteAdapter(DryRunWriteAdapter):
    """SQLite write adapter skeleton.

    R40 does not write to production SQLite. This class validates payloads and
    returns dry-run results only.
    """

    backend_name = "sqlite"


class SupabaseWriteAdapter(DryRunWriteAdapter):
    """Supabase write adapter skeleton.

    This class intentionally performs no Supabase insert/update/delete. It can
    validate payloads without requiring secrets. If a future isolated write test
    needs a client, it must be added behind an explicit test-only path.
    """

    backend_name = "supabase"

    def __init__(self, require_env: bool = False) -> None:
        self.supabase_url = os.environ.get("SUPABASE_URL")
        self.service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if require_env and (not self.supabase_url or not self.service_role_key):
            raise RuntimeError(
                "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. "
                "Supabase write adapter skeleton skipped."
            )


def get_write_backend_name() -> str:
    backend = os.environ.get(WRITE_BACKEND_ENV, "sqlite").strip().lower() or "sqlite"
    if backend in SUPPORTED_WRITE_BACKENDS:
        return backend
    raise ValueError(f"Unsupported {WRITE_BACKEND_ENV}: {backend}")


def get_write_adapter(backend: str | None = None) -> WriteAdapter:
    backend_name = (backend or get_write_backend_name()).strip().lower()
    if backend_name == "sqlite":
        return SQLiteWriteAdapter()
    if backend_name == "supabase":
        return SupabaseWriteAdapter()
    raise ValueError(f"Unsupported write backend: {backend_name}")
