#!/usr/bin/env python3
"""One-time CSV to Supabase import tool for PGY90 Health Coach."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT_DIR / "exports"
VALIDATION_SCRIPT = ROOT_DIR / "scripts" / "validate_supabase_import.py"
VALIDATION_REPORT = EXPORT_DIR / "import_validation_report.txt"
SUMMARY_PATH = EXPORT_DIR / "supabase_import_summary.txt"

TABLE_ORDER = [
    "people",
    "app_users",
    "coach_profiles",
    "daily_logs",
    "meal_logs",
    "weekly_reports",
]

CSV_FILES = {
    "people": "people.csv",
    "app_users": "app_users.csv",
    "coach_profiles": "coach_profiles.csv",
    "daily_logs": "daily_logs.csv",
    "meal_logs": "meal_logs.csv",
    "weekly_reports": "weekly_reports.csv",
}

NUMERIC_FIELDS = {
    "daily_logs": {
        "weight_kg": float,
        "body_fat_percent": float,
        "waist_cm": float,
        "sleep_hours": float,
        "sleep_quality": int,
        "workout_minutes": int,
        "avg_heart_rate": int,
        "max_heart_rate": int,
        "active_calories": int,
        "distance_km": float,
        "rpe": int,
        "systolic_bp": int,
        "diastolic_bp": int,
        "pulse_bpm": int,
    },
    "meal_logs": {
        "id": int,
        "calories": int,
        "protein_g": float,
        "fiber_g": float,
        "carbs_g": float,
        "fat_g": float,
    },
    "coach_profiles": {
        "current_weight_kg": float,
        "daily_calorie_target": int,
        "protein_target_g": int,
        "fiber_target_g": int,
        "height_cm": float,
        "target_weight_kg": float,
        "target_body_fat_min": float,
        "target_body_fat_max": float,
        "birth_year": int,
    },
}

BOOLEAN_FIELDS = {
    "daily_logs": {"rehab_done"},
}

BOOLEAN_TRUE = {"1", "true", "True", "yes", "Y"}
BOOLEAN_FALSE = {"0", "false", "False", "no", "N"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import exported PGY90 CSV files into Supabase."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read CSV and Supabase counts without writing any data.",
    )
    parser.add_argument(
        "--allow-nonempty",
        action="store_true",
        help="Allow import when target Supabase tables already contain rows.",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip running scripts/validate_supabase_import.py before import.",
    )
    return parser.parse_args()


def env_or_error() -> tuple[str, str]:
    supabase_url = os.environ.get("SUPABASE_URL")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    missing = []
    if not supabase_url:
        missing.append("SUPABASE_URL")
    if not service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")

    if missing:
        print("ERROR: Missing required environment variables:", file=sys.stderr)
        for name in missing:
            print(f"- {name}", file=sys.stderr)
        print("", file=sys.stderr)
        print('export SUPABASE_URL="https://xxxxx.supabase.co"', file=sys.stderr)
        print('export SUPABASE_SERVICE_ROLE_KEY="your-service-role-or-secret-key"', file=sys.stderr)
        raise SystemExit(1)

    return supabase_url, service_role_key


def read_csv_rows(table_name: str) -> list[dict[str, Any]]:
    path = EXPORT_DIR / CSV_FILES[table_name]
    if not path.exists():
        raise FileNotFoundError(f"Missing CSV for {table_name}: {path}")

    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return [normalize_row(table_name, dict(row)) for row in reader]


def normalize_row(table_name: str, row: dict[str, str]) -> dict[str, Any]:
    numeric_fields = NUMERIC_FIELDS.get(table_name, {})
    boolean_fields = BOOLEAN_FIELDS.get(table_name, set())
    normalized: dict[str, Any] = {}

    for field, raw_value in row.items():
        value = raw_value.strip() if isinstance(raw_value, str) else raw_value
        if value == "":
            normalized[field] = None
            continue

        if field in numeric_fields:
            normalized[field] = numeric_fields[field](value)
            continue

        if field in boolean_fields:
            if value in BOOLEAN_TRUE:
                normalized[field] = True
            elif value in BOOLEAN_FALSE:
                normalized[field] = False
            else:
                normalized[field] = None
            continue

        normalized[field] = value

    return normalized


def run_validation() -> str:
    result = subprocess.run(
        [sys.executable, str(VALIDATION_SCRIPT)],
        cwd=ROOT_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError("Import validation script failed.")

    return read_validation_status()


def read_validation_status() -> str:
    if not VALIDATION_REPORT.exists():
        raise RuntimeError(
            "Validation report not found. Run python3 scripts/validate_supabase_import.py first."
        )

    for line in VALIDATION_REPORT.read_text(encoding="utf-8").splitlines():
        if line.startswith("Final status:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("Validation report does not contain a final status.")


def create_supabase_client(supabase_url: str, service_role_key: str):
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: supabase. Install project requirements first."
        ) from exc

    return create_client(supabase_url, service_role_key)


def count_table(client, table_name: str) -> int:
    response = client.table(table_name).select("*", count="exact").limit(0).execute()
    count = getattr(response, "count", None)
    return int(count) if count is not None else 0


def insert_rows(client, table_name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    # Keep batches small enough for PostgREST payload limits and easier failure isolation.
    batch_size = 500
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        client.table(table_name).insert(batch).execute()


def write_summary(
    *,
    dry_run: bool,
    status: str,
    csv_counts: dict[str, int],
    before_counts: dict[str, int],
    after_counts: dict[str, int],
    errors: list[str],
    warnings: list[str],
) -> None:
    lines = [
        "PGY90 Supabase Import Summary",
        "=" * 35,
        f"Import time: {datetime.now().isoformat(timespec='seconds')}",
        f"Mode: {'dry-run' if dry_run else 'import'}",
        f"Final status: {status}",
        "",
        "CSV row counts:",
    ]
    for table_name in TABLE_ORDER:
        lines.append(f"- {table_name}: {csv_counts.get(table_name, 0)}")

    lines.extend(["", "Supabase row counts before:"])
    for table_name in TABLE_ORDER:
        lines.append(f"- {table_name}: {before_counts.get(table_name, 'unknown')}")

    lines.extend(["", "Supabase row counts after:"])
    for table_name in TABLE_ORDER:
        lines.append(f"- {table_name}: {after_counts.get(table_name, 'not run')}")

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
            "- This script does not modify local CSV files or SQLite data.",
            "- This script never truncates or deletes Supabase data.",
        ]
    )
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    csv_rows: dict[str, list[dict[str, Any]]] = {}
    csv_counts: dict[str, int] = {}
    before_counts: dict[str, int] = {}
    after_counts: dict[str, int] = {}

    try:
        supabase_url, service_role_key = env_or_error()

        if not EXPORT_DIR.exists():
            raise RuntimeError(f"Exports directory not found: {EXPORT_DIR}")

        if args.skip_validation:
            validation_status = read_validation_status()
            warnings.append("Validation script was skipped; using existing validation report.")
        else:
            validation_status = run_validation()

        if validation_status != "PASS":
            raise RuntimeError(f"Validation status is {validation_status}; import requires PASS.")

        for table_name in TABLE_ORDER:
            rows = read_csv_rows(table_name)
            csv_rows[table_name] = rows
            csv_counts[table_name] = len(rows)

        client = create_supabase_client(supabase_url, service_role_key)

        for table_name in TABLE_ORDER:
            before_counts[table_name] = count_table(client, table_name)

        nonempty_tables = {
            table_name: count
            for table_name, count in before_counts.items()
            if count > 0
        }
        if nonempty_tables and not args.dry_run and not args.allow_nonempty:
            details = ", ".join(f"{name}={count}" for name, count in nonempty_tables.items())
            raise RuntimeError(
                "Supabase target tables are not empty. "
                f"Use --allow-nonempty only after manual review. Nonempty: {details}"
            )
        if nonempty_tables and args.dry_run:
            details = ", ".join(f"{name}={count}" for name, count in nonempty_tables.items())
            warnings.append(f"Dry-run found nonempty target tables: {details}")

        if args.dry_run:
            after_counts = dict(before_counts)
            status = "PASS"
        else:
            for table_name in TABLE_ORDER:
                insert_rows(client, table_name, csv_rows[table_name])
                after_counts[table_name] = count_table(client, table_name)

            for table_name in TABLE_ORDER:
                expected = before_counts[table_name] + csv_counts[table_name]
                actual = after_counts.get(table_name)
                if actual != expected:
                    errors.append(
                        f"{table_name}: expected {expected} rows after import, found {actual}"
                    )

            status = "FAIL" if errors else "PASS"

    except Exception as exc:
        errors.append(str(exc))
        status = "FAIL"

    try:
        write_summary(
            dry_run=args.dry_run,
            status=status,
            csv_counts=csv_counts,
            before_counts=before_counts,
            after_counts=after_counts,
            errors=errors,
            warnings=warnings,
        )
    except Exception as summary_exc:
        errors.append(f"Failed to write summary: {summary_exc}")

    print("PGY90 Supabase import tool completed.")
    print(f"Mode: {'dry-run' if args.dry_run else 'import'}")
    print(f"Status: {status}")
    print("CSV row counts:")
    for table_name in TABLE_ORDER:
        print(f"- {table_name}: {csv_counts.get(table_name, 0)}")
    print("Supabase row counts before:")
    for table_name in TABLE_ORDER:
        print(f"- {table_name}: {before_counts.get(table_name, 'unknown')}")
    print("Supabase row counts after:")
    for table_name in TABLE_ORDER:
        print(f"- {table_name}: {after_counts.get(table_name, 'not run')}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print(f"Summary: {SUMMARY_PATH.relative_to(ROOT_DIR)}")

    if errors:
        print("Error summary:", file=sys.stderr)
        for message in errors:
            print(f"- {message}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
