#!/usr/bin/env python3
"""Post-cutover read-only safety check for PGY90 Supabase data.

This script only reads Supabase tables. It does not write to Supabase, SQLite,
CSV files, exports, or any application data.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db_adapter import CORE_TABLES, SupabaseAdapter
from runtime_config import BACKEND_FLAG_DEFAULTS, get_backend_flag


PERSON_REF_TABLES = [
    "app_users",
    "coach_profiles",
    "daily_logs",
    "meal_logs",
    "weekly_reports",
]

HARD_KEY_FIELDS = {
    "daily_logs": ["person_name", "log_date"],
    "meal_logs": ["id"],
    "weekly_reports": ["person_name", "week_start"],
}

MEAL_SOFT_DUPLICATE_FIELDS = [
    "person_name",
    "log_date",
    "meal_type",
    "description",
    "calories",
]

RECENT_FIELDS = {
    "daily_logs": ["person_name", "log_date", "weight_kg", "sleep_hours", "updated_at", "created_at"],
    "meal_logs": ["id", "person_name", "log_date", "meal_type", "calories", "updated_at", "created_at"],
    "weekly_reports": ["person_name", "week_start", "week_end", "generated_at"],
}


def rows_for_table(adapter: SupabaseAdapter, table_name: str) -> list[dict[str, Any]]:
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


def normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def key_for(row: dict[str, Any], fields: list[str]) -> tuple[str, ...]:
    return tuple(normalize(row.get(field)) for field in fields)


def label_key(key: tuple[str, ...]) -> str:
    return " | ".join(key)


def duplicate_keys(rows: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    counts = Counter(key_for(row, fields) for row in rows)
    duplicates = []
    for key, count in counts.items():
        if count > 1 or any(part == "" for part in key):
            duplicates.append({"key": label_key(key), "count": count})
    return duplicates


def person_names(rows: list[dict[str, Any]]) -> set[str]:
    return {normalize(row.get("person_name")) for row in rows if normalize(row.get("person_name"))}


def safe_row(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {field: row.get(field) for field in fields if field in row}


def recent_rows(rows: list[dict[str, Any]], table_name: str, limit: int = 5) -> list[dict[str, Any]]:
    if table_name == "daily_logs":
        sort_fields = ["log_date", "updated_at", "created_at"]
    elif table_name == "meal_logs":
        sort_fields = ["created_at", "updated_at", "log_date", "id"]
    else:
        sort_fields = ["generated_at", "week_start"]

    def sort_key(row: dict[str, Any]) -> tuple[str, ...]:
        return tuple(normalize(row.get(field)) for field in sort_fields)

    return [safe_row(row, RECENT_FIELDS[table_name]) for row in sorted(rows, key=sort_key, reverse=True)[:limit]]


def final_status(errors: list[str], warnings: list[str], skipped: bool) -> str:
    if skipped:
        return "WARNING"
    if errors:
        return "FAIL"
    if warnings:
        return "WARNING"
    return "PASS"


def run_check() -> dict[str, Any]:
    checked_at = datetime.now().isoformat(timespec="seconds")
    errors: list[str] = []
    warnings: list[str] = []
    skipped = False
    rows_by_table: dict[str, list[dict[str, Any]]] = {}

    result: dict[str, Any] = {
        "checked_at": checked_at,
        "cutover_flags": {flag: get_backend_flag(flag) for flag in BACKEND_FLAG_DEFAULTS},
        "row_counts": {},
        "duplicates": {},
        "soft_warnings": {},
        "recent_rows": {},
        "orphans": {},
        "errors": errors,
        "warnings": warnings,
    }

    try:
        adapter = SupabaseAdapter()
    except Exception as exc:
        skipped = True
        warnings.append(
            "Supabase safety check skipped: missing or invalid SUPABASE_URL / "
            f"SUPABASE_SERVICE_ROLE_KEY ({exc})"
        )
        result["status"] = final_status(errors, warnings, skipped)
        result["skipped"] = skipped
        return result

    for table_name in CORE_TABLES:
        try:
            rows = rows_for_table(adapter, table_name)
        except Exception as exc:
            errors.append(f"{table_name}: read failed ({exc})")
            rows = []
        rows_by_table[table_name] = rows
        result["row_counts"][table_name] = len(rows)

    if result["row_counts"].get("people", 0) == 0:
        errors.append("people: row count is 0 after cutover")
    if result["row_counts"].get("app_users", 0) == 0:
        errors.append("app_users: row count is 0 after cutover")

    for table_name, fields in HARD_KEY_FIELDS.items():
        duplicates = duplicate_keys(rows_by_table.get(table_name, []), fields)
        result["duplicates"][table_name] = duplicates
        if duplicates:
            errors.append(f"{table_name}: duplicate or blank hard key found")

    meal_soft_dupes = duplicate_keys(rows_by_table.get("meal_logs", []), MEAL_SOFT_DUPLICATE_FIELDS)
    result["soft_warnings"]["meal_logs_possible_duplicates"] = meal_soft_dupes
    if meal_soft_dupes:
        warnings.append("meal_logs: possible duplicate meal entries found; review manually")

    people = person_names(rows_by_table.get("people", []))
    for table_name in PERSON_REF_TABLES:
        refs = person_names(rows_by_table.get(table_name, []))
        missing = sorted(refs - people)
        result["orphans"][table_name] = missing
        if missing:
            errors.append(f"{table_name}: person_name missing from people ({', '.join(missing)})")

    for table_name in ["daily_logs", "meal_logs", "weekly_reports"]:
        result["recent_rows"][table_name] = recent_rows(rows_by_table.get(table_name, []), table_name)

    result["status"] = final_status(errors, warnings, skipped)
    result["skipped"] = skipped
    return result


def print_text(result: dict[str, Any]) -> None:
    print("PGY90 post-cutover safety check")
    print(f"Checked at: {result['checked_at']}")
    print(f"Status: {result['status']}")
    print("")

    print("Cutover flags:")
    for flag, value in result["cutover_flags"].items():
        print(f"- {flag}: {value}")
    print("")

    print("Row counts:")
    for table_name in CORE_TABLES:
        print(f"- {table_name}: {result['row_counts'].get(table_name, 'not checked')}")
    print("")

    print("Duplicate hard key checks:")
    for table_name in ["daily_logs", "meal_logs", "weekly_reports"]:
        duplicates = result["duplicates"].get(table_name, [])
        print(f"- {table_name}: {len(duplicates)}")
        for duplicate in duplicates[:10]:
            print(f"  - {duplicate['key']} ({duplicate['count']})")
    print("")

    print("Orphan person_name checks:")
    for table_name in PERSON_REF_TABLES:
        missing = result["orphans"].get(table_name, [])
        print(f"- {table_name}: {', '.join(missing) if missing else 'ok'}")
    print("")

    print("Recent writes:")
    for table_name in ["daily_logs", "meal_logs", "weekly_reports"]:
        print(f"- {table_name}:")
        rows = result["recent_rows"].get(table_name, [])
        if not rows:
            print("  - none")
        for row in rows:
            print(f"  - {row}")
    print("")

    print("Warnings:")
    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"- {warning}")
    else:
        print("- None")
    print("")

    print("Errors:")
    if result["errors"]:
        for error in result["errors"]:
            print(f"- {error}")
    else:
        print("- None")
    print("")
    print("Safety: read-only check; no Supabase writes; no SQLite/CSV/export changes; no secrets printed.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PGY90 post-cutover Supabase safety checks.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = run_check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_text(result)

    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
