#!/usr/bin/env python3
"""Smoke-test read-only dashboard read models without writing data."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard_read_models import (
    get_latest_daily_log,
    get_latest_meal_entries,
    get_latest_weight_entries,
    get_person_daily_logs,
    get_person_meal_logs,
    get_person_weekly_reports,
)


TEST_PERSON = "TYP"


def compact_row(row: dict[str, Any] | None, fields: list[str]) -> dict[str, Any]:
    if not row:
        return {}
    return {field: row.get(field) for field in fields if field in row}


def print_backend_summary(backend: str) -> None:
    latest_daily = get_latest_daily_log(TEST_PERSON, backend=backend)
    recent_daily = get_person_daily_logs(TEST_PERSON, limit=3, backend=backend)
    recent_meals = get_person_meal_logs(TEST_PERSON, limit=3, backend=backend)
    recent_weekly = get_person_weekly_reports(TEST_PERSON, limit=3, backend=backend)
    weight_entries = get_latest_weight_entries(TEST_PERSON, limit=3, backend=backend)
    meal_entries = get_latest_meal_entries(TEST_PERSON, limit=3, backend=backend)

    print(f"Backend: {backend}")
    print(f"- latest daily log: {compact_row(latest_daily, ['person_name', 'log_date', 'weight_kg', 'sleep_hours'])}")
    print(f"- recent daily logs: {len(recent_daily)}")
    for row in recent_daily:
        print(f"  - {compact_row(row, ['person_name', 'log_date', 'weight_kg', 'systolic_bp', 'diastolic_bp'])}")
    print(f"- recent meal logs: {len(recent_meals)}")
    for row in recent_meals:
        print(f"  - {compact_row(row, ['id', 'person_name', 'log_date', 'calories', 'protein_g'])}")
    print(f"- recent weekly reports: {len(recent_weekly)}")
    for row in recent_weekly:
        print(f"  - {compact_row(row, ['person_name', 'week_start', 'week_end', 'generated_at'])}")
    print(f"- recent weight entries: {len(weight_entries)}")
    print(f"- latest meal entries: {len(meal_entries)}")


def has_supabase_env() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def main() -> int:
    print("PGY90 dashboard read model smoke test")
    print_backend_summary("sqlite")

    if not has_supabase_env():
        print("Backend: supabase")
        print("- skipped: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing.")
        return 0

    try:
        print_backend_summary("supabase")
    except Exception as exc:
        print(f"ERROR: Supabase read model test failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
