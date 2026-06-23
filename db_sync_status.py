"""Read-only SQLite / Supabase sync status helper for admin diagnostics."""

from __future__ import annotations

from typing import Any

from db_adapter import CORE_TABLES, SQLiteAdapter, SupabaseAdapter


KEY_FIELDS = {
    "people": ["person_name"],
    "app_users": ["person_name"],
    "coach_profiles": ["person_name"],
    "daily_logs": ["person_name", "log_date"],
    "meal_logs": ["id"],
    "weekly_reports": ["person_name", "week_start"],
}


def rows_for_table(adapter: SQLiteAdapter | SupabaseAdapter, table_name: str) -> list[dict[str, Any]]:
    if table_name == "people":
        return adapter.list_people()
    if table_name == "app_users":
        return adapter.get_app_users()
    if table_name == "coach_profiles":
        return adapter.get_coach_profiles()
    if table_name == "daily_logs":
        return adapter.get_daily_logs()
    if table_name == "meal_logs":
        return adapter.get_meal_logs()
    if table_name == "weekly_reports":
        return adapter.get_weekly_reports()
    raise ValueError(f"Unsupported table: {table_name}")


def normalize_key_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def row_key(table_name: str, row: dict[str, Any]) -> tuple[str, ...]:
    fields = KEY_FIELDS[table_name]
    if table_name == "meal_logs" and not normalize_key_value(row.get("id")):
        fields = ["person_name", "log_date", "created_at", "description"]
    return tuple(normalize_key_value(row.get(field)) for field in fields)


def compare_rows(table_name: str, sqlite_rows: list[dict[str, Any]], supabase_rows: list[dict[str, Any]]) -> dict[str, Any]:
    sqlite_keys = {row_key(table_name, row) for row in sqlite_rows}
    supabase_keys = {row_key(table_name, row) for row in supabase_rows}
    missing = sqlite_keys - supabase_keys
    extra = supabase_keys - sqlite_keys
    return {
        "table": table_name,
        "sqlite_count": len(sqlite_rows),
        "supabase_count": len(supabase_rows),
        "missing_in_supabase": len(missing),
        "extra_in_supabase": len(extra),
        "status": "OK" if not missing and not extra else "DIFF",
    }


def get_sqlite_supabase_sync_status() -> dict[str, Any]:
    """Return read-only sync status for admin diagnostics.

    This helper never writes to SQLite or Supabase.
    """

    errors: list[str] = []
    warnings: list[str] = []
    table_rows: list[dict[str, Any]] = []

    try:
        sqlite_adapter = SQLiteAdapter()
        sqlite_by_table = {
            table_name: rows_for_table(sqlite_adapter, table_name)
            for table_name in CORE_TABLES
        }
    except Exception as exc:
        return {
            "overall_status": "ERROR",
            "rows": [],
            "errors": [f"SQLite 讀取失敗：{exc}"],
            "warnings": warnings,
        }

    try:
        supabase_adapter = SupabaseAdapter()
        supabase_by_table = {
            table_name: rows_for_table(supabase_adapter, table_name)
            for table_name in CORE_TABLES
        }
    except Exception as exc:
        message = str(exc)
        if "SUPABASE_URL" in message or "SUPABASE_SERVICE_ROLE_KEY" in message:
            message = "Supabase 同步狀態目前無法檢查：缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY。"
        return {
            "overall_status": "ERROR",
            "rows": [
                {
                    "table": table_name,
                    "sqlite_count": len(sqlite_by_table.get(table_name, [])),
                    "supabase_count": "未檢查",
                    "missing_in_supabase": "未檢查",
                    "extra_in_supabase": "未檢查",
                    "status": "未檢查",
                }
                for table_name in CORE_TABLES
            ],
            "errors": [message],
            "warnings": warnings,
        }

    for table_name in CORE_TABLES:
        table_rows.append(
            compare_rows(
                table_name,
                sqlite_by_table.get(table_name, []),
                supabase_by_table.get(table_name, []),
            )
        )

    has_diff = any(row["status"] != "OK" for row in table_rows)
    return {
        "overall_status": "DIFF_FOUND" if has_diff else "PASS",
        "rows": table_rows,
        "errors": errors,
        "warnings": warnings,
    }
