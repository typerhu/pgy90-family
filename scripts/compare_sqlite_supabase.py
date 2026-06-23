#!/usr/bin/env python3
"""Compare local SQLite rows with the current Supabase snapshot.

This is a read-only migration safety tool. It does not write to SQLite,
Supabase, CSV files, or the Streamlit app.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import DB_PATH
from db_adapter import CORE_TABLES, SQLiteAdapter, SupabaseAdapter


REPORT_PATH = ROOT_DIR / "exports" / "sqlite_supabase_diff_report.txt"

KEY_FIELDS = {
    "people": ["person_name"],
    "app_users": ["person_name"],
    "coach_profiles": ["person_name"],
    "daily_logs": ["person_name", "log_date"],
    "meal_logs": ["id"],
    "weekly_reports": ["person_name", "week_start"],
}

PERSON_REF_TABLES = [
    "app_users",
    "coach_profiles",
    "daily_logs",
    "meal_logs",
    "weekly_reports",
]


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


def key_label(key: tuple[str, ...]) -> str:
    return " | ".join(key)


def duplicate_keys(table_name: str, rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts = Counter(row_key(table_name, row) for row in rows)
    return [(key_label(key), count) for key, count in counts.items() if count > 1 or any(part == "" for part in key)]


def compare_table(
    table_name: str,
    sqlite_rows: list[dict[str, Any]],
    supabase_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    sqlite_keys = {row_key(table_name, row) for row in sqlite_rows}
    supabase_keys = {row_key(table_name, row) for row in supabase_rows}

    missing = sorted(sqlite_keys - supabase_keys)
    extra = sorted(supabase_keys - sqlite_keys)
    common = sqlite_keys & supabase_keys

    return {
        "sqlite_count": len(sqlite_rows),
        "supabase_count": len(supabase_rows),
        "missing": [key_label(key) for key in missing],
        "extra": [key_label(key) for key in extra],
        "common_count": len(common),
        "sqlite_duplicate_keys": duplicate_keys(table_name, sqlite_rows),
        "supabase_duplicate_keys": duplicate_keys(table_name, supabase_rows),
    }


def person_names(rows: list[dict[str, Any]]) -> set[str]:
    return {normalize_key_value(row.get("person_name")) for row in rows if normalize_key_value(row.get("person_name"))}


def check_person_refs(
    source_name: str,
    table_rows: dict[str, list[dict[str, Any]]],
    errors: list[str],
    warnings: list[str],
) -> dict[str, list[str]]:
    people = person_names(table_rows.get("people", []))
    results: dict[str, list[str]] = {}

    if not people and table_rows.get("people"):
        errors.append(f"{source_name}: people rows exist but person_name values could not be read")

    for table_name in PERSON_REF_TABLES:
        refs = person_names(table_rows.get(table_name, []))
        missing = sorted(refs - people)
        results[table_name] = missing
        if missing:
            errors.append(
                f"{source_name}: {table_name} has person_name values missing from people: {', '.join(missing)}"
            )
    return results


def write_report(
    *,
    status: str,
    comparisons: dict[str, dict[str, Any]],
    sqlite_ref_results: dict[str, list[str]],
    supabase_ref_results: dict[str, list[str]],
    errors: list[str],
    warnings: list[str],
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "PGY90 SQLite vs Supabase Diff Report",
        "=" * 39,
        f"Compared at: {datetime.now().isoformat(timespec='seconds')}",
        f"SQLite DB path: {DB_PATH}",
        f"Final status: {status}",
        "",
        "Compared tables:",
    ]
    for table_name in CORE_TABLES:
        lines.append(f"- {table_name}")

    lines.extend(["", "Summary:"])
    for table_name in CORE_TABLES:
        result = comparisons.get(table_name, {})
        lines.append(
            "- "
            f"{table_name}: SQLite {result.get('sqlite_count', 'unknown')} / "
            f"Supabase {result.get('supabase_count', 'unknown')} / "
            f"common {result.get('common_count', 'unknown')} / "
            f"missing_in_supabase {len(result.get('missing', []))} / "
            f"extra_in_supabase {len(result.get('extra', []))}"
        )

    lines.extend(["", "Missing in Supabase keys:"])
    for table_name in CORE_TABLES:
        missing = comparisons.get(table_name, {}).get("missing", [])
        lines.append(f"- {table_name}:")
        if missing:
            lines.extend(f"  - {key}" for key in missing)
        else:
            lines.append("  - None")

    lines.extend(["", "Extra in Supabase keys:"])
    for table_name in CORE_TABLES:
        extra = comparisons.get(table_name, {}).get("extra", [])
        lines.append(f"- {table_name}:")
        if extra:
            lines.extend(f"  - {key}" for key in extra)
        else:
            lines.append("  - None")

    lines.extend(["", "Duplicate key checks:"])
    for table_name in CORE_TABLES:
        result = comparisons.get(table_name, {})
        sqlite_dupes = result.get("sqlite_duplicate_keys", [])
        supabase_dupes = result.get("supabase_duplicate_keys", [])
        lines.append(f"- {table_name}:")
        lines.append(f"  - SQLite: {sqlite_dupes if sqlite_dupes else 'None'}")
        lines.append(f"  - Supabase: {supabase_dupes if supabase_dupes else 'None'}")

    lines.extend(["", "person_name reference checks:"])
    lines.append("- SQLite:")
    for table_name in PERSON_REF_TABLES:
        missing = sqlite_ref_results.get(table_name, [])
        lines.append(f"  - {table_name}: {missing if missing else 'ok'}")
    lines.append("- Supabase:")
    for table_name in PERSON_REF_TABLES:
        missing = supabase_ref_results.get(table_name, [])
        lines.append(f"  - {table_name}: {missing if missing else 'ok'}")

    lines.extend(["", "Errors:"])
    if errors:
        lines.extend(f"- {message}" for message in errors)
    else:
        lines.append("- None")

    lines.extend(["", "Warnings:"])
    if warnings:
        lines.extend(f"- {message}" for message in warnings)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "Safety notes:",
            "- This report is stored in exports/ and should not be committed to GitHub.",
            "- Supabase URL and service role key are intentionally not written here.",
            "- This script only reads SQLite and Supabase data.",
            "- This script does not insert, update, delete, upsert, truncate, or modify data.",
            "- This script does not modify local CSV files.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def final_status(comparisons: dict[str, dict[str, Any]], errors: list[str]) -> str:
    if errors:
        return "FAIL"
    for result in comparisons.values():
        if result.get("missing") or result.get("extra"):
            return "DIFF_FOUND"
    return "PASS"


def main() -> int:
    comparisons: dict[str, dict[str, Any]] = {}
    sqlite_rows_by_table: dict[str, list[dict[str, Any]]] = {}
    supabase_rows_by_table: dict[str, list[dict[str, Any]]] = {}
    sqlite_ref_results: dict[str, list[str]] = {}
    supabase_ref_results: dict[str, list[str]] = {}
    errors: list[str] = []
    warnings: list[str] = []

    try:
        sqlite_adapter = SQLiteAdapter()
        for table_name in CORE_TABLES:
            sqlite_rows_by_table[table_name] = rows_for_table(sqlite_adapter, table_name)

        supabase_adapter = SupabaseAdapter()

        for table_name in CORE_TABLES:
            supabase_rows_by_table[table_name] = rows_for_table(supabase_adapter, table_name)
            comparisons[table_name] = compare_table(
                table_name,
                sqlite_rows_by_table[table_name],
                supabase_rows_by_table[table_name],
            )

        for table_name, result in comparisons.items():
            for key, count in result.get("sqlite_duplicate_keys", []):
                errors.append(f"SQLite {table_name}: duplicate or blank key {key} ({count} rows)")
            for key, count in result.get("supabase_duplicate_keys", []):
                errors.append(f"Supabase {table_name}: duplicate or blank key {key} ({count} rows)")

        sqlite_ref_results = check_person_refs("SQLite", sqlite_rows_by_table, errors, warnings)
        supabase_ref_results = check_person_refs("Supabase", supabase_rows_by_table, errors, warnings)
    except Exception as exc:
        errors.append(str(exc))

    for table_name in CORE_TABLES:
        if table_name not in comparisons:
            comparisons[table_name] = {
                "sqlite_count": len(sqlite_rows_by_table.get(table_name, [])),
                "supabase_count": "unknown",
                "missing": [],
                "extra": [],
                "common_count": "unknown",
                "sqlite_duplicate_keys": duplicate_keys(table_name, sqlite_rows_by_table.get(table_name, [])),
                "supabase_duplicate_keys": [],
            }

    status = final_status(comparisons, errors)
    try:
        write_report(
            status=status,
            comparisons=comparisons,
            sqlite_ref_results=sqlite_ref_results,
            supabase_ref_results=supabase_ref_results,
            errors=errors,
            warnings=warnings,
        )
    except Exception as report_exc:
        errors.append(f"Failed to write report: {report_exc}")
        status = "FAIL"

    print("PGY90 SQLite vs Supabase comparison completed.")
    print(f"Status: {status}")
    print("Row counts:")
    for table_name in CORE_TABLES:
        result = comparisons.get(table_name, {})
        print(
            "- "
            f"{table_name}: SQLite {result.get('sqlite_count', 'unknown')} / "
            f"Supabase {result.get('supabase_count', 'unknown')} / "
            f"missing {len(result.get('missing', []))} / "
            f"extra {len(result.get('extra', []))}"
        )
    print("Report:")
    print(f"- {REPORT_PATH.relative_to(ROOT_DIR)}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")

    if errors:
        print("Error summary:", file=sys.stderr)
        for message in errors:
            print(f"- {message}", file=sys.stderr)

    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
