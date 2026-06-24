#!/usr/bin/env python3
"""Smoke-test PGY90 write adapter skeleton without writing data."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from write_adapter import (
    SupabaseWriteAdapter,
    build_daily_log_payload,
    build_meal_log_payload,
    build_weekly_report_payload,
    get_write_adapter,
)


def scrub_result(result) -> dict:
    return {
        "backend": result.backend,
        "operation": result.operation,
        "table": result.table,
        "key": result.key,
        "dry_run": result.dry_run,
        "would_write": result.would_write,
        "payload_fields": sorted(result.payload.keys()),
        "message": result.message,
    }


def has_supabase_env() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def main() -> int:
    print("PGY90 write adapter skeleton smoke test")

    payload = build_weekly_report_payload(
        person_name="TYP",
        week_start="2026-06-22",
        week_end="2026-06-28",
        summary="Test summary for dry-run validation only.",
        generated_at="2026-06-24T07:30:00",
    )
    print(f"- weekly report payload fields: {sorted(payload.keys())}")

    sqlite_adapter = get_write_adapter("sqlite")
    sqlite_result = sqlite_adapter.save_weekly_report(**payload)
    print(f"- sqlite dry-run: {scrub_result(sqlite_result)}")
    if not sqlite_result.dry_run or not sqlite_result.would_write:
        print("ERROR: SQLite adapter did not return dry-run result.", file=sys.stderr)
        return 1

    supabase_adapter = get_write_adapter("supabase")
    supabase_result = supabase_adapter.save_weekly_report(**payload)
    print(f"- supabase dry-run: {scrub_result(supabase_result)}")
    if not supabase_result.dry_run or not supabase_result.would_write:
        print("ERROR: Supabase adapter did not return dry-run result.", file=sys.stderr)
        return 1

    daily_payload = build_daily_log_payload(
        {
            "person_name": "TYP",
            "log_date": "2026-06-24",
            "weight_kg": 82.1,
            "sleep_hours": 6.5,
            "rehab_done": 1,
            "ignored_field": "not exported",
        }
    )
    print(f"- daily log payload fields: {sorted(daily_payload.keys())}")
    daily_result = supabase_adapter.upsert_daily_log(daily_payload)
    print(f"- supabase daily_logs dry-run: {scrub_result(daily_result)}")
    if not daily_result.dry_run or not daily_result.would_write:
        print("ERROR: Supabase daily_logs adapter did not return dry-run result.", file=sys.stderr)
        return 1

    meal_payload = build_meal_log_payload(
        {
            "id": 12345,
            "person_name": "TYP",
            "log_date": "2026-06-24",
            "meal_type": "test",
            "description": "R44 dry-run meal log payload.",
            "calories": 123,
            "protein_g": 12.0,
            "fiber_g": 3.0,
            "carbs_g": 20.0,
            "fat_g": 4.0,
            "confidence": "dry-run",
            "created_at": "2026-06-24T08:00:00",
            "ignored_field": "not exported",
        }
    )
    chinese_meal_payload = build_meal_log_payload(
        {
            "id": 12346,
            "person_name": "TYP",
            "log_date": "2026-06-24",
            "meal_type": "午餐",
            "description": "彩椒雞蛋番茄什錦",
            "calories": 123,
            "protein_g": 12.5,
            "fiber_g": 3.0,
            "carbs_g": 18.0,
            "fat_g": 5.0,
            "confidence": "中文 dry-run",
            "created_at": "2026-06-24T08:10:00",
        }
    )
    print(f"- meal log payload fields: {sorted(meal_payload.keys())}")
    print(f"- chinese meal log payload fields: {sorted(chinese_meal_payload.keys())}")
    try:
        import json

        json.dumps(chinese_meal_payload, ensure_ascii=False).encode("utf-8")
        print("- chinese meal log UTF-8 serialization: PASS")
    except UnicodeError as exc:
        print(f"ERROR: Chinese meal payload UTF-8 serialization failed: {exc}", file=sys.stderr)
        return 1
    meal_save_result = supabase_adapter.save_meal_log(meal_payload)
    meal_update_result = supabase_adapter.update_meal_log(int(meal_payload["id"]), meal_payload)
    meal_delete_result = supabase_adapter.delete_meal_log(int(meal_payload["id"]), "TYP")
    chinese_meal_result = supabase_adapter.save_meal_log(chinese_meal_payload)
    print(f"- supabase meal_logs save dry-run: {scrub_result(meal_save_result)}")
    print(f"- supabase meal_logs update dry-run: {scrub_result(meal_update_result)}")
    print(f"- supabase meal_logs delete dry-run: {scrub_result(meal_delete_result)}")
    print(f"- supabase chinese meal_logs save dry-run: {scrub_result(chinese_meal_result)}")
    if not all(
        result.dry_run and result.would_write
        for result in [meal_save_result, meal_update_result, meal_delete_result, chinese_meal_result]
    ):
        print("ERROR: Supabase meal_logs adapter did not return dry-run results.", file=sys.stderr)
        return 1

    if has_supabase_env():
        SupabaseWriteAdapter(require_env=True)
        print("- supabase env check: present, no write attempted")
    else:
        print("- supabase env check: skipped, SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing")

    print("No SQLite or Supabase writes were performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
