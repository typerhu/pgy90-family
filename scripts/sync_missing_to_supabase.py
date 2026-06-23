#!/usr/bin/env python3
"""Insert SQLite rows that are missing from Supabase.

This is a guarded one-way catch-up tool for the PGY90 migration. It only
inserts rows whose keys exist in SQLite and not in Supabase.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db_adapter import CORE_TABLES, SQLiteAdapter, SupabaseAdapter
from scripts.compare_sqlite_supabase import key_label, row_key, rows_for_table


REPORT_PATH = ROOT_DIR / "exports" / "sqlite_supabase_sync_report.txt"

BOOLEAN_FIELDS = {
    "daily_logs": {"rehab_done"},
}

BOOLEAN_TRUE = {1, "1", "true", "True", "yes", "Y", True}
BOOLEAN_FALSE = {0, "0", "false", "False", "no", "N", False}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert SQLite rows that are missing from Supabase."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show missing rows without inserting anything.",
    )
    return parser.parse_args()


def normalize_value(table_name: str, field: str, value: Any) -> Any:
    if value == "":
        return None
    if field in BOOLEAN_FIELDS.get(table_name, set()):
        if value in BOOLEAN_TRUE:
            return True
        if value in BOOLEAN_FALSE:
            return False
        return None
    return value


def normalize_row_for_supabase(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        field: normalize_value(table_name, field, value)
        for field, value in row.items()
    }


def missing_rows(
    table_name: str,
    sqlite_rows: list[dict[str, Any]],
    supabase_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    supabase_keys = {row_key(table_name, row) for row in supabase_rows}
    return [
        row
        for row in sqlite_rows
        if row_key(table_name, row) not in supabase_keys
    ]


def extra_keys(
    table_name: str,
    sqlite_rows: list[dict[str, Any]],
    supabase_rows: list[dict[str, Any]],
) -> list[str]:
    sqlite_keys = {row_key(table_name, row) for row in sqlite_rows}
    supabase_keys = {row_key(table_name, row) for row in supabase_rows}
    return [key_label(key) for key in sorted(supabase_keys - sqlite_keys)]


def insert_missing_rows(
    supabase_adapter: SupabaseAdapter,
    table_name: str,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0

    normalized_rows = [
        normalize_row_for_supabase(table_name, row)
        for row in rows
    ]

    batch_size = 500
    inserted = 0
    for start in range(0, len(normalized_rows), batch_size):
        batch = normalized_rows[start : start + batch_size]
        supabase_adapter.client.table(table_name).insert(batch).execute()
        inserted += len(batch)
    return inserted


def write_report(
    *,
    mode: str,
    status: str,
    sqlite_counts: dict[str, int],
    supabase_before_counts: dict[str, int],
    supabase_after_counts: dict[str, int | str],
    missing_by_table: dict[str, list[dict[str, Any]]],
    inserted_by_table: dict[str, list[str]],
    extra_by_table: dict[str, list[str]],
    errors: list[str],
    warnings: list[str],
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "PGY90 SQLite to Supabase Sync Report",
        "=" * 39,
        f"Synced at: {datetime.now().isoformat(timespec='seconds')}",
        f"Mode: {mode}",
        f"Final status: {status}",
        "",
        "Summary:",
    ]
    for table_name in CORE_TABLES:
        missing_keys = [key_label(row_key(table_name, row)) for row in missing_by_table.get(table_name, [])]
        lines.append(
            "- "
            f"{table_name}: SQLite {sqlite_counts.get(table_name, 'unknown')} / "
            f"Supabase before {supabase_before_counts.get(table_name, 'unknown')} / "
            f"missing {len(missing_keys)} / "
            f"inserted {len(inserted_by_table.get(table_name, []))} / "
            f"Supabase after {supabase_after_counts.get(table_name, 'not run')} / "
            f"extra {len(extra_by_table.get(table_name, []))}"
        )

    lines.extend(["", "Missing keys:"])
    for table_name in CORE_TABLES:
        missing_keys = [key_label(row_key(table_name, row)) for row in missing_by_table.get(table_name, [])]
        lines.append(f"- {table_name}:")
        if missing_keys:
            lines.extend(f"  - {key}" for key in missing_keys)
        else:
            lines.append("  - None")

    lines.extend(["", "Inserted keys:"])
    for table_name in CORE_TABLES:
        inserted = inserted_by_table.get(table_name, [])
        lines.append(f"- {table_name}:")
        if inserted:
            lines.extend(f"  - {key}" for key in inserted)
        else:
            lines.append("  - None")

    lines.extend(["", "Extra in Supabase keys:"])
    for table_name in CORE_TABLES:
        extra = extra_by_table.get(table_name, [])
        lines.append(f"- {table_name}:")
        if extra:
            lines.extend(f"  - {key}" for key in extra)
        else:
            lines.append("  - None")

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
            "- This script only inserts missing rows in sync mode.",
            "- This script never updates, deletes, upserts, truncates, or overwrites data.",
            "- This script does not modify SQLite or CSV files.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def final_status(dry_run: bool, missing_by_table: dict[str, list[dict[str, Any]]], errors: list[str]) -> str:
    if errors:
        return "FAIL"
    has_missing = any(rows for rows in missing_by_table.values())
    if dry_run and has_missing:
        return "DRY_RUN_DIFF_FOUND"
    return "PASS"


def main() -> int:
    args = parse_args()
    mode = "dry-run" if args.dry_run else "sync"
    sqlite_counts: dict[str, int] = {}
    supabase_before_counts: dict[str, int] = {}
    supabase_after_counts: dict[str, int | str] = {}
    missing_by_table: dict[str, list[dict[str, Any]]] = {}
    inserted_by_table: dict[str, list[str]] = {table_name: [] for table_name in CORE_TABLES}
    extra_by_table: dict[str, list[str]] = {}
    errors: list[str] = []
    warnings: list[str] = []

    try:
        sqlite_adapter = SQLiteAdapter()
        sqlite_rows_by_table = {
            table_name: rows_for_table(sqlite_adapter, table_name)
            for table_name in CORE_TABLES
        }
        for table_name in CORE_TABLES:
            sqlite_counts[table_name] = len(sqlite_rows_by_table[table_name])

        supabase_adapter = SupabaseAdapter()

        supabase_rows_by_table = {
            table_name: rows_for_table(supabase_adapter, table_name)
            for table_name in CORE_TABLES
        }

        for table_name in CORE_TABLES:
            sqlite_rows = sqlite_rows_by_table[table_name]
            supabase_rows = supabase_rows_by_table[table_name]
            supabase_before_counts[table_name] = len(supabase_rows)
            missing_by_table[table_name] = missing_rows(table_name, sqlite_rows, supabase_rows)
            extra_by_table[table_name] = extra_keys(table_name, sqlite_rows, supabase_rows)
            if extra_by_table[table_name]:
                warnings.append(
                    f"{table_name}: Supabase has {len(extra_by_table[table_name])} extra row(s); no delete will be performed."
                )

        if args.dry_run:
            supabase_after_counts = dict(supabase_before_counts)
        else:
            for table_name in CORE_TABLES:
                rows = missing_by_table[table_name]
                inserted_count = insert_missing_rows(supabase_adapter, table_name, rows)
                inserted_by_table[table_name] = [
                    key_label(row_key(table_name, row))
                    for row in rows[:inserted_count]
                ]

            after_counts = supabase_adapter.table_counts()
            for table_name in CORE_TABLES:
                supabase_after_counts[table_name] = after_counts[table_name]
                if supabase_after_counts[table_name] != sqlite_counts[table_name]:
                    errors.append(
                        f"{table_name}: after sync Supabase count {supabase_after_counts[table_name]} "
                        f"does not match SQLite count {sqlite_counts[table_name]}"
                    )

    except Exception as exc:
        errors.append(str(exc))

    status = final_status(args.dry_run, missing_by_table, errors)
    try:
        write_report(
            mode=mode,
            status=status,
            sqlite_counts=sqlite_counts,
            supabase_before_counts=supabase_before_counts,
            supabase_after_counts=supabase_after_counts,
            missing_by_table=missing_by_table,
            inserted_by_table=inserted_by_table,
            extra_by_table=extra_by_table,
            errors=errors,
            warnings=warnings,
        )
    except Exception as report_exc:
        errors.append(f"Failed to write report: {report_exc}")
        status = "FAIL"

    print("PGY90 SQLite to Supabase missing-row sync completed.")
    print(f"Mode: {mode}")
    print(f"Status: {status}")
    print("Row counts:")
    for table_name in CORE_TABLES:
        print(
            "- "
            f"{table_name}: SQLite {sqlite_counts.get(table_name, 'unknown')} / "
            f"Supabase before {supabase_before_counts.get(table_name, 'unknown')} / "
            f"missing {len(missing_by_table.get(table_name, []))} / "
            f"inserted {len(inserted_by_table.get(table_name, []))} / "
            f"Supabase after {supabase_after_counts.get(table_name, 'not run')}"
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
