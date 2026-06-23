#!/usr/bin/env python3
"""Read-only Supabase verification tool for PGY90 Health Coach migration."""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT_DIR / "exports"
REPORT_PATH = EXPORT_DIR / "supabase_read_verification_report.txt"

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

PERSON_REF_TABLES = [
    "app_users",
    "coach_profiles",
    "daily_logs",
    "meal_logs",
    "weekly_reports",
]


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


def create_supabase_client(supabase_url: str, service_role_key: str):
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: supabase. Install project requirements first."
        ) from exc

    return create_client(supabase_url, service_role_key)


def read_csv_count(table_name: str, warnings: list[str]) -> int | None:
    if not EXPORT_DIR.exists():
        warnings.append(f"Exports directory not found: {EXPORT_DIR}")
        return None

    path = EXPORT_DIR / CSV_FILES[table_name]
    if not path.exists():
        warnings.append(f"CSV not found for {table_name}: {path.relative_to(ROOT_DIR)}")
        return None

    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return sum(1 for _ in reader)


def count_table(client, table_name: str) -> int:
    response = client.table(table_name).select("*", count="exact").limit(0).execute()
    count = getattr(response, "count", None)
    return int(count) if count is not None else 0


def read_sample(client, table_name: str) -> list[dict[str, Any]]:
    query = client.table(table_name).select("*")

    if table_name in {"people", "app_users", "coach_profiles"}:
        query = query.order("person_name")
    elif table_name == "daily_logs":
        query = query.order("person_name").order("log_date")
    elif table_name == "meal_logs":
        query = query.order("person_name").order("created_at")
    elif table_name == "weekly_reports":
        query = query.order("person_name").order("week_start")

    response = query.limit(3).execute()
    data = getattr(response, "data", None)
    return list(data or [])


def read_person_names(client, table_name: str) -> list[str]:
    response = client.table(table_name).select("person_name").limit(10000).execute()
    rows = list(getattr(response, "data", None) or [])
    names = []
    for row in rows:
        person_name = row.get("person_name")
        if person_name:
            names.append(str(person_name))
    return names


def final_status(errors: list[str], warnings: list[str]) -> str:
    if errors:
        return "FAIL"
    if warnings:
        return "PASS_WITH_WARNINGS"
    return "PASS"


def write_report(
    *,
    status: str,
    csv_counts: dict[str, int | None],
    supabase_counts: dict[str, int],
    count_matches: dict[str, str],
    sample_status: dict[str, str],
    person_ref_status: dict[str, str],
    errors: list[str],
    warnings: list[str],
) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "PGY90 Supabase Read Verification Report",
        "=" * 43,
        f"Verified at: {datetime.now().isoformat(timespec='seconds')}",
        f"Final status: {status}",
        "",
        "Row counts:",
    ]
    for table_name in TABLE_ORDER:
        csv_count = csv_counts.get(table_name)
        csv_text = "missing" if csv_count is None else str(csv_count)
        supabase_count = supabase_counts.get(table_name, "unknown")
        match_text = count_matches.get(table_name, "not checked")
        lines.append(f"- {table_name}: Supabase={supabase_count}, CSV={csv_text}, match={match_text}")

    lines.extend(["", "Sample read checks:"])
    for table_name in TABLE_ORDER:
        lines.append(f"- {table_name}: {sample_status.get(table_name, 'not checked')}")

    lines.extend(["", "person_name reference checks:"])
    for table_name in PERSON_REF_TABLES:
        lines.append(f"- {table_name}: {person_ref_status.get(table_name, 'not checked')}")

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
            "- This script only reads Supabase data.",
            "- This script does not insert, update, delete, upsert, truncate, or modify data.",
            "- This script does not modify local CSV files or SQLite data.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    csv_counts: dict[str, int | None] = {}
    supabase_counts: dict[str, int] = {}
    count_matches: dict[str, str] = {}
    sample_status: dict[str, str] = {}
    person_ref_status: dict[str, str] = {}

    try:
        supabase_url, service_role_key = env_or_error()
        client = create_supabase_client(supabase_url, service_role_key)

        for table_name in TABLE_ORDER:
            csv_counts[table_name] = read_csv_count(table_name, warnings)

        for table_name in TABLE_ORDER:
            supabase_counts[table_name] = count_table(client, table_name)

        for table_name in TABLE_ORDER:
            csv_count = csv_counts.get(table_name)
            supabase_count = supabase_counts.get(table_name)
            if csv_count is None:
                count_matches[table_name] = "not checked"
            elif supabase_count == csv_count:
                count_matches[table_name] = "yes"
            else:
                count_matches[table_name] = "no"
                errors.append(
                    f"{table_name}: Supabase count {supabase_count} does not match CSV count {csv_count}"
                )

        for table_name in TABLE_ORDER:
            sample = read_sample(client, table_name)
            if supabase_counts.get(table_name, 0) > 0 and not sample:
                sample_status[table_name] = "failed"
                errors.append(f"{table_name}: row count is nonzero but sample read returned no rows")
            else:
                sample_status[table_name] = f"ok ({len(sample)} sampled)"

        people_names = set(read_person_names(client, "people"))
        if not people_names and supabase_counts.get("people", 0) > 0:
            errors.append("people: count is nonzero but person_name values could not be read")

        for table_name in PERSON_REF_TABLES:
            names = read_person_names(client, table_name)
            missing = sorted({name for name in names if name not in people_names})
            if missing:
                person_ref_status[table_name] = f"failed ({len(missing)} missing person_name values)"
                errors.append(
                    f"{table_name}: person_name values missing from people: {', '.join(missing)}"
                )
            else:
                person_ref_status[table_name] = "ok"

    except Exception as exc:
        errors.append(str(exc))

    status = final_status(errors, warnings)
    try:
        write_report(
            status=status,
            csv_counts=csv_counts,
            supabase_counts=supabase_counts,
            count_matches=count_matches,
            sample_status=sample_status,
            person_ref_status=person_ref_status,
            errors=errors,
            warnings=warnings,
        )
    except Exception as report_exc:
        errors.append(f"Failed to write report: {report_exc}")
        status = "FAIL"

    print("PGY90 Supabase read verification completed.")
    print(f"Status: {status}")
    print("Row counts:")
    for table_name in TABLE_ORDER:
        print(f"- {table_name}: {supabase_counts.get(table_name, 'unknown')}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print(f"Report: {REPORT_PATH.relative_to(ROOT_DIR)}")

    if errors:
        print("Error summary:", file=sys.stderr)
        for message in errors:
            print(f"- {message}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
