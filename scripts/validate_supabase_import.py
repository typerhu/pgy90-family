#!/usr/bin/env python3
"""Validate exported PGY90 SQLite CSV files before Supabase import."""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT_DIR / "exports"
SCHEMA_PATH = ROOT_DIR / "supabase" / "schema.sql"
REPORT_PATH = EXPORT_DIR / "import_validation_report.txt"


TABLES = {
    "people": {
        "file": "people.csv",
        "expected": ["person_name", "created_at"],
        "required": ["person_name", "created_at"],
        "key": ["person_name"],
        "date_fields": ["created_at"],
        "numeric_fields": [],
        "boolean_fields": [],
    },
    "app_users": {
        "file": "app_users.csv",
        "expected": ["person_name", "password_salt", "password_hash", "created_at"],
        "required": ["person_name", "password_salt", "password_hash", "created_at"],
        "key": ["person_name"],
        "date_fields": ["created_at"],
        "numeric_fields": [],
        "boolean_fields": [],
        "person_ref": True,
    },
    "daily_logs": {
        "file": "daily_logs.csv",
        "expected": [
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
        ],
        "required": ["person_name", "log_date", "created_at", "updated_at"],
        "key": ["person_name", "log_date"],
        "date_fields": ["log_date", "created_at", "updated_at"],
        "numeric_fields": [
            "weight_kg",
            "body_fat_percent",
            "waist_cm",
            "sleep_hours",
            "sleep_quality",
            "workout_minutes",
            "avg_heart_rate",
            "max_heart_rate",
            "active_calories",
            "distance_km",
            "rpe",
            "systolic_bp",
            "diastolic_bp",
            "pulse_bpm",
        ],
        "boolean_fields": ["rehab_done"],
        "person_ref": True,
    },
    "meal_logs": {
        "file": "meal_logs.csv",
        "expected": [
            "id",
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
            "person_name",
        ],
        "required": ["id", "log_date", "meal_type", "description", "confidence", "created_at", "person_name"],
        "key": ["id"],
        "date_fields": ["log_date", "created_at"],
        "numeric_fields": ["id", "calories", "protein_g", "fiber_g", "carbs_g", "fat_g"],
        "boolean_fields": [],
        "person_ref": True,
    },
    "coach_profiles": {
        "file": "coach_profiles.csv",
        "expected": [
            "person_name",
            "goal",
            "current_weight_kg",
            "daily_calorie_target",
            "protein_target_g",
            "fiber_target_g",
            "preferences",
            "updated_at",
            "height_cm",
            "target_weight_kg",
            "target_body_fat_min",
            "target_body_fat_max",
            "gender",
            "birth_year",
            "activity_level",
            "health_limitations",
        ],
        "required": ["person_name", "goal", "updated_at"],
        "key": ["person_name"],
        "date_fields": ["updated_at"],
        "numeric_fields": [
            "current_weight_kg",
            "daily_calorie_target",
            "protein_target_g",
            "fiber_target_g",
            "height_cm",
            "target_weight_kg",
            "target_body_fat_min",
            "target_body_fat_max",
            "birth_year",
        ],
        "boolean_fields": [],
        "person_ref": True,
    },
    "weekly_reports": {
        "file": "weekly_reports.csv",
        "expected": ["person_name", "week_start", "week_end", "summary", "generated_at"],
        "required": ["person_name", "week_start", "week_end", "summary", "generated_at"],
        "key": ["person_name", "week_start"],
        "date_fields": ["week_start", "week_end", "generated_at"],
        "numeric_fields": [],
        "boolean_fields": [],
        "person_ref": True,
    },
}
REQUIRED_SCHEMA_TABLES = set(TABLES)

LEGACY_TABLE = {
    "name": "coach_profile_legacy",
    "file": "coach_profile_legacy.csv",
    "expected": [
        "id",
        "goal",
        "current_weight_kg",
        "daily_calorie_target",
        "protein_target_g",
        "fiber_target_g",
        "preferences",
        "updated_at",
    ],
    "required": ["id", "goal", "updated_at"],
    "key": ["id"],
    "date_fields": ["updated_at"],
    "numeric_fields": [
        "id",
        "current_weight_kg",
        "daily_calorie_target",
        "protein_target_g",
        "fiber_target_g",
    ],
    "boolean_fields": [],
}

BOOLEAN_VALUES = {"0", "1", "true", "false", "True", "False", "yes", "no", "Y", "N", ""}


def is_blank(value: str | None) -> bool:
    return value is None or value == ""


def is_valid_date_or_datetime(value: str) -> bool:
    if is_blank(value):
        return False

    normalized = value.strip()
    if not normalized:
        return False

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        try:
            date.fromisoformat(normalized)
            return True
        except ValueError:
            return False

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        datetime.fromisoformat(normalized)
        return True
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            datetime.strptime(normalized, fmt)
            return True
        except ValueError:
            continue

    return False


def can_parse_number(value: str) -> bool:
    if is_blank(value):
        return True
    try:
        float(value)
        return True
    except ValueError:
        return False


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        headers = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return headers, rows


def read_schema_tables(path: Path) -> set[str]:
    if not path.exists():
        return set()
    schema_sql = path.read_text(encoding="utf-8")
    return {
        match.group(1)
        for match in re.finditer(
            r"create\s+table\s+if\s+not\s+exists\s+public\.([a-zA-Z_][a-zA-Z0-9_]*)",
            schema_sql,
            flags=re.IGNORECASE,
        )
    }


def add_section(lines: list[str], title: str) -> None:
    lines.extend(["", title, "-" * len(title)])


def validate_header(
    table_name: str,
    headers: list[str],
    expected: list[str],
    required: list[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    header_set = set(headers)
    expected_set = set(expected)

    for field in required:
        if field not in header_set:
            errors.append(f"{table_name}: missing required column {field}")

    optional_missing = sorted(expected_set - header_set - set(required))
    for field in optional_missing:
        warnings.append(f"{table_name}: missing optional expected column {field}")

    extra = sorted(header_set - expected_set)
    for field in extra:
        warnings.append(f"{table_name}: extra column {field}")


def validate_required_values(
    table_name: str,
    rows: list[dict[str, str]],
    required: list[str],
    errors: list[str],
) -> None:
    for index, row in enumerate(rows, start=2):
        for field in required:
            if field in row and is_blank(row.get(field, "")):
                errors.append(f"{table_name}: blank required value at CSV row {index}, column {field}")


def validate_unique_key(
    table_name: str,
    rows: list[dict[str, str]],
    key_fields: list[str],
    errors: list[str],
) -> None:
    if not key_fields:
        return

    key_counts: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        if any(field not in row for field in key_fields):
            return
        key = tuple((row.get(field) or "").strip() for field in key_fields)
        key_counts[key] += 1

    for key, count in key_counts.items():
        if any(part == "" for part in key):
            errors.append(f"{table_name}: blank primary/unique key {key_fields} -> {key}")
        if count > 1:
            errors.append(f"{table_name}: duplicate primary/unique key {key_fields} -> {key} ({count} rows)")


def validate_date_fields(
    table_name: str,
    rows: list[dict[str, str]],
    fields: list[str],
    required: list[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    for index, row in enumerate(rows, start=2):
        for field in fields:
            if field not in row:
                continue
            value = (row.get(field) or "").strip()
            if is_blank(value):
                if field in required:
                    errors.append(f"{table_name}: blank required date/datetime at row {index}, column {field}")
                else:
                    warnings.append(f"{table_name}: blank optional date/datetime at row {index}, column {field}")
                continue
            if not is_valid_date_or_datetime(value):
                errors.append(f"{table_name}: invalid date/datetime at row {index}, column {field}: {value}")


def validate_boolean_fields(
    table_name: str,
    rows: list[dict[str, str]],
    fields: list[str],
    warnings: list[str],
) -> None:
    for index, row in enumerate(rows, start=2):
        for field in fields:
            if field not in row:
                continue
            value = (row.get(field) or "").strip()
            if value not in BOOLEAN_VALUES:
                warnings.append(f"{table_name}: non-standard boolean at row {index}, column {field}: {value}")


def validate_numeric_fields(
    table_name: str,
    rows: list[dict[str, str]],
    fields: list[str],
    errors: list[str],
) -> None:
    for index, row in enumerate(rows, start=2):
        for field in fields:
            if field not in row:
                continue
            value = (row.get(field) or "").strip()
            if not can_parse_number(value):
                errors.append(f"{table_name}: non-numeric value at row {index}, column {field}: {value}")


def validate_person_references(
    table_name: str,
    rows: list[dict[str, str]],
    people_names: set[str],
    errors: list[str],
) -> None:
    if "person_name" not in rows[0] if rows else False:
        return
    missing_refs: dict[str, int] = defaultdict(int)
    for row in rows:
        person_name = (row.get("person_name") or "").strip()
        if person_name and person_name not in people_names:
            missing_refs[person_name] += 1
    for person_name, count in sorted(missing_refs.items()):
        errors.append(f"{table_name}: person_name {person_name!r} is not present in people.csv ({count} rows)")


def validate_table(
    table_name: str,
    config: dict[str, object],
    required_core: bool,
    people_names: set[str],
    errors: list[str],
    warnings: list[str],
) -> tuple[bool, int, list[str]]:
    path = EXPORT_DIR / str(config["file"])
    if not path.exists():
        message = f"{table_name}: missing CSV file {path.relative_to(ROOT_DIR)}"
        if required_core:
            errors.append(message)
        else:
            warnings.append(message)
        return False, 0, []

    headers, rows = read_csv_rows(path)
    expected = list(config["expected"])
    required = list(config["required"])

    validate_header(table_name, headers, expected, required, errors, warnings)
    validate_required_values(table_name, rows, required, errors)
    validate_unique_key(table_name, rows, list(config["key"]), errors)
    validate_date_fields(table_name, rows, list(config["date_fields"]), required, errors, warnings)
    validate_boolean_fields(table_name, rows, list(config["boolean_fields"]), warnings)
    validate_numeric_fields(table_name, rows, list(config["numeric_fields"]), errors)

    if config.get("person_ref"):
        validate_person_references(table_name, rows, people_names, errors)

    return True, len(rows), headers


def final_status(errors: list[str], warnings: list[str]) -> str:
    if errors:
        return "FAIL"
    if warnings:
        return "PASS_WITH_WARNINGS"
    return "PASS"


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    row_counts: dict[str, int] = {}
    file_status: dict[str, str] = {}
    schema_status = "present" if SCHEMA_PATH.exists() else "missing"

    if not EXPORT_DIR.exists():
        print(f"ERROR: export directory not found at {EXPORT_DIR}", file=sys.stderr)
        return 1

    people_names: set[str] = set()
    people_path = EXPORT_DIR / str(TABLES["people"]["file"])
    if people_path.exists():
        _, people_rows = read_csv_rows(people_path)
        people_names = {(row.get("person_name") or "").strip() for row in people_rows if row.get("person_name")}

    schema_tables = read_schema_tables(SCHEMA_PATH)
    if schema_status == "missing":
        errors.append(f"Supabase schema file not found at {SCHEMA_PATH}")
    else:
        missing_schema_tables = sorted(REQUIRED_SCHEMA_TABLES - schema_tables)
        for table_name in missing_schema_tables:
            errors.append(f"Supabase schema is missing table public.{table_name}")

    for table_name, config in TABLES.items():
        exists, count, _ = validate_table(table_name, config, True, people_names, errors, warnings)
        file_status[table_name] = "present" if exists else "missing"
        row_counts[table_name] = count

    legacy_exists, legacy_count, _ = validate_table(
        str(LEGACY_TABLE["name"]),
        LEGACY_TABLE,
        False,
        people_names,
        errors,
        warnings,
    )
    file_status[str(LEGACY_TABLE["name"])] = "present (legacy, not imported)" if legacy_exists else "missing (legacy optional)"
    row_counts[str(LEGACY_TABLE["name"])] = legacy_count

    status = final_status(errors, warnings)
    checked_at = datetime.now().isoformat(timespec="seconds")

    lines: list[str] = [
        "PGY90 Supabase Import Validation Report",
        "=" * 43,
        f"Checked at: {checked_at}",
        f"Supabase schema: {schema_status} -> {SCHEMA_PATH}",
        f"Exports directory: {EXPORT_DIR}",
        f"Final status: {status}",
    ]

    add_section(lines, "CSV file status")
    for table_name, status_text in file_status.items():
        lines.append(f"- {table_name}: {status_text}")

    add_section(lines, "Supabase schema tables")
    if schema_tables:
        for table_name in sorted(schema_tables):
            lines.append(f"- public.{table_name}")
    else:
        lines.append("- None")

    add_section(lines, "Row counts")
    for table_name, count in row_counts.items():
        lines.append(f"- {table_name}: {count}")

    add_section(lines, "Errors")
    if errors:
        for message in errors:
            lines.append(f"- {message}")
    else:
        lines.append("- None")

    add_section(lines, "Warnings")
    if warnings:
        for message in warnings:
            lines.append(f"- {message}")
    else:
        lines.append("- None")

    add_section(lines, "Checks performed")
    lines.extend(
        [
            "- Core CSV existence",
            "- Header required/missing/extra columns",
            "- Row counts",
            "- Primary key and unique key duplicates",
            "- Date and datetime formats",
            "- Boolean cast candidates",
            "- Numeric cast candidates",
            "- person_name references against people.csv",
            "- Legacy coach_profile CSV marked as non-import target",
        ]
    )

    add_section(lines, "Safety notes")
    lines.extend(
        [
            "- This script only reads exports/*.csv and supabase/schema.sql.",
            "- This script does not connect to Supabase.",
            "- This script does not modify CSV files.",
            "- This script does not modify SQLite data.",
            "- exports/import_validation_report.txt may mention personal data keys and must not be committed.",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("PGY90 Supabase import validation completed.")
    print(f"Status: {status}")
    print("Row counts:")
    for table_name, count in row_counts.items():
        print(f"- {table_name}: {count}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print(f"Report: {REPORT_PATH.relative_to(ROOT_DIR)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
