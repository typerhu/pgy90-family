"""Write adapter skeleton for future PGY90 Supabase cutover.

This module is intentionally not wired into the Streamlit app. It does not
write to production SQLite. Supabase writes are limited to the explicit
weekly_reports pilot path introduced after the isolated R41 test.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


WRITE_BACKEND_ENV = "PGY90_WRITE_BACKEND"
SUPPORTED_WRITE_BACKENDS = {"sqlite", "supabase"}
DAILY_LOG_COLUMNS = {
    "person_name",
    "log_date",
    "weight_kg",
    "body_fat_percent",
    "waist_cm",
    "sleep_hours",
    "sleep_quality",
    "food_category",
    "food_notes",
    "breakfast_category",
    "breakfast_notes",
    "lunch_category",
    "lunch_notes",
    "dinner_category",
    "dinner_notes",
    "snack_notes",
    "workout_type",
    "workout_minutes",
    "avg_heart_rate",
    "max_heart_rate",
    "active_calories",
    "distance_km",
    "rpe",
    "discomfort_notes",
    "workout_notes",
    "rehab_done",
    "rehab_type",
    "rehab_notes",
    "notes",
    "created_at",
    "updated_at",
    "systolic_bp",
    "diastolic_bp",
    "pulse_bpm",
}
MEAL_LOG_COLUMNS = {
    "id",
    "person_name",
    "log_date",
    "meal_type",
    "description",
    "calories",
    "protein_g",
    "fiber_g",
    "carbs_g",
    "fat_g",
    "confidence",
    "created_at",
}


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


def _blank_to_none(value: Any) -> Any:
    if value == "":
        return None
    return value


def _bool_or_none(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    cleaned = str(value).strip().lower()
    if cleaned in {"1", "true", "yes", "y"}:
        return True
    if cleaned in {"0", "false", "no", "n"}:
        return False
    return bool(value)


def build_daily_log_payload(values: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    payload = {
        key: _blank_to_none(value)
        for key, value in dict(values).items()
        if key in DAILY_LOG_COLUMNS
    }
    payload["person_name"] = _required_text(payload.get("person_name"), "person_name")
    payload["log_date"] = _required_text(payload.get("log_date"), "log_date")
    payload["updated_at"] = payload.get("updated_at") or now
    payload["created_at"] = payload.get("created_at") or payload["updated_at"]
    if "rehab_done" in payload:
        payload["rehab_done"] = _bool_or_none(payload.get("rehab_done"))
    return payload


def build_meal_log_payload(values: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: _blank_to_none(value)
        for key, value in dict(values).items()
        if key in MEAL_LOG_COLUMNS
    }
    payload["person_name"] = _required_text(payload.get("person_name"), "person_name")
    payload["log_date"] = _required_text(payload.get("log_date"), "log_date")
    payload["meal_type"] = _required_text(payload.get("meal_type"), "meal_type")
    payload["description"] = _required_text(payload.get("description"), "description")
    payload["confidence"] = _required_text(payload.get("confidence"), "confidence")
    payload["created_at"] = payload.get("created_at") or datetime.now().isoformat(timespec="seconds")
    if payload.get("id") is not None:
        payload["id"] = int(payload["id"])
    return payload


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
        payload = build_daily_log_payload(values)
        return self._result(
            operation="upsert_daily_log",
            table="daily_logs",
            key={"person_name": payload["person_name"], "log_date": payload["log_date"]},
            payload=payload,
            message="Skeleton only. Future implementation must define upsert semantics.",
        )

    def save_meal_log(self, values: dict[str, Any]) -> WriteResult:
        payload = build_meal_log_payload(values)
        return self._result(
            operation="save_meal_log",
            table="meal_logs",
            key={"id": payload.get("id")},
            payload=payload,
            message="Skeleton only. Future implementation must define id handling.",
        )

    def update_meal_log(self, meal_id: int, values: dict[str, Any]) -> WriteResult:
        if int(meal_id) <= 0:
            raise ValueError("meal_id must be positive.")
        payload = build_meal_log_payload({**values, "id": int(meal_id)})
        return self._result(
            operation="update_meal_log",
            table="meal_logs",
            key={"id": int(meal_id)},
            payload=payload,
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
    """Supabase write adapter.

    By default this class remains dry-run for smoke tests. Passing dry_run=False
    enables the weekly_reports and daily_logs pilot paths. Other write methods
    still use the inherited skeleton behavior.
    """

    backend_name = "supabase"

    def __init__(self, require_env: bool = False, dry_run: bool = True) -> None:
        self.supabase_url = os.environ.get("SUPABASE_URL")
        self.service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        self.dry_run = dry_run
        if require_env and (not self.supabase_url or not self.service_role_key):
            raise RuntimeError(
                "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. "
                "Supabase write adapter skeleton skipped."
            )
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if not self.supabase_url or not self.service_role_key:
            raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
        if self._client is None:
            try:
                from supabase import create_client
            except ImportError as exc:
                raise RuntimeError("The supabase package is required for Supabase writes.") from exc
            self._client = create_client(self.supabase_url, self.service_role_key)
        return self._client

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
        key = {"person_name": payload["person_name"], "week_start": payload["week_start"]}
        if self.dry_run:
            return self._result(
                operation="save_weekly_report",
                table="weekly_reports",
                key=key,
                payload=payload,
            )

        client = self._get_client()
        client.table("weekly_reports").upsert(
            payload,
            on_conflict="person_name,week_start",
        ).execute()
        return WriteResult(
            backend=self.backend_name,
            operation="save_weekly_report",
            table="weekly_reports",
            key=key,
            payload=payload,
            dry_run=False,
            would_write=True,
            message="Supabase weekly_reports upsert completed.",
        )

    def upsert_daily_log(self, values: dict[str, Any]) -> WriteResult:
        payload = build_daily_log_payload(values)
        key = {"person_name": payload["person_name"], "log_date": payload["log_date"]}
        if self.dry_run:
            return self._result(
                operation="upsert_daily_log",
                table="daily_logs",
                key=key,
                payload=payload,
            )

        client = self._get_client()
        client.table("daily_logs").upsert(
            payload,
            on_conflict="person_name,log_date",
        ).execute()
        return WriteResult(
            backend=self.backend_name,
            operation="upsert_daily_log",
            table="daily_logs",
            key=key,
            payload=payload,
            dry_run=False,
            would_write=True,
            message="Supabase daily_logs upsert completed.",
        )

    def save_meal_log(self, values: dict[str, Any]) -> WriteResult:
        payload = build_meal_log_payload(values)
        key = {"id": payload.get("id")}
        if self.dry_run:
            return self._result(
                operation="save_meal_log",
                table="meal_logs",
                key=key,
                payload=payload,
            )

        client = self._get_client()
        client.table("meal_logs").upsert(payload, on_conflict="id").execute()
        return WriteResult(
            backend=self.backend_name,
            operation="save_meal_log",
            table="meal_logs",
            key=key,
            payload=payload,
            dry_run=False,
            would_write=True,
            message="Supabase meal_logs upsert completed.",
        )

    def update_meal_log(self, meal_id: int, values: dict[str, Any]) -> WriteResult:
        if int(meal_id) <= 0:
            raise ValueError("meal_id must be positive.")
        payload = build_meal_log_payload({**values, "id": int(meal_id)})
        key = {"id": int(meal_id)}
        if self.dry_run:
            return self._result(
                operation="update_meal_log",
                table="meal_logs",
                key=key,
                payload=payload,
            )

        client = self._get_client()
        client.table("meal_logs").upsert(payload, on_conflict="id").execute()
        return WriteResult(
            backend=self.backend_name,
            operation="update_meal_log",
            table="meal_logs",
            key=key,
            payload=payload,
            dry_run=False,
            would_write=True,
            message="Supabase meal_logs update upsert completed.",
        )

    def delete_meal_log(self, meal_id: int, person_name: str | None = None) -> WriteResult:
        if int(meal_id) <= 0:
            raise ValueError("meal_id must be positive.")
        key: dict[str, Any] = {"id": int(meal_id)}
        if person_name:
            key["person_name"] = person_name
        if self.dry_run:
            return self._result(
                operation="delete_meal_log",
                table="meal_logs",
                key=key,
                message="Validated only. No data was deleted.",
            )

        query = self._get_client().table("meal_logs").delete().eq("id", int(meal_id))
        if person_name:
            query = query.eq("person_name", person_name)
        query.execute()
        return WriteResult(
            backend=self.backend_name,
            operation="delete_meal_log",
            table="meal_logs",
            key=key,
            payload={},
            dry_run=False,
            would_write=True,
            message="Supabase meal_logs delete completed.",
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
