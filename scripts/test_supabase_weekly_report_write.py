#!/usr/bin/env python3
"""R41 isolated Supabase weekly_reports write test.

This script is intentionally separate from the Streamlit app. It only writes a
clearly marked test row when --execute is provided, then deletes that same test
row before reporting success.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from write_adapter import build_weekly_report_payload


TABLE_NAME = "weekly_reports"
TEST_PERSON_NAME = "__R41_TEST__"
TEST_WEEK_START = "2099-01-01"
TEST_WEEK_END = "2099-01-07"
TEST_GENERATED_AT = "2099-01-01T00:00:00"
TEST_SUMMARY = "R41 isolated Supabase weekly report write test"
UPDATED_TEST_SUMMARY = f"{TEST_SUMMARY} - updated"


def has_supabase_env() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def create_supabase_client() -> Any:
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError("The supabase package is required for --execute mode.") from exc

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(url, key)


def build_test_payload(summary: str = TEST_SUMMARY) -> dict[str, Any]:
    return build_weekly_report_payload(
        person_name=TEST_PERSON_NAME,
        week_start=TEST_WEEK_START,
        week_end=TEST_WEEK_END,
        summary=summary,
        generated_at=TEST_GENERATED_AT,
    )


def select_test_rows(client: Any) -> list[dict[str, Any]]:
    response = (
        client.table(TABLE_NAME)
        .select("*")
        .eq("person_name", TEST_PERSON_NAME)
        .eq("week_start", TEST_WEEK_START)
        .execute()
    )
    return list(getattr(response, "data", None) or [])


def cleanup_test_row(client: Any) -> bool:
    (
        client.table(TABLE_NAME)
        .delete()
        .eq("person_name", TEST_PERSON_NAME)
        .eq("week_start", TEST_WEEK_START)
        .execute()
    )
    return len(select_test_rows(client)) == 0


def run_dry_run() -> dict[str, str]:
    payload = build_test_payload()
    required_fields = ["person_name", "week_start", "week_end", "summary", "generated_at"]
    missing = [field for field in required_fields if not payload.get(field)]
    if missing:
        return {
            "insert": "SKIPPED",
            "read": "SKIPPED",
            "update": "SKIPPED",
            "cleanup": "SKIPPED",
            "final": "FAIL",
            "message": f"Payload validation failed. Missing fields: {', '.join(missing)}",
        }

    return {
        "insert": "SKIPPED",
        "read": "SKIPPED",
        "update": "SKIPPED",
        "cleanup": "SKIPPED",
        "final": "PASS",
        "message": (
            "Dry-run payload validated for weekly_reports test key "
            f"{TEST_PERSON_NAME} | {TEST_WEEK_START}. No Supabase connection or write was attempted."
        ),
    }


def run_execute() -> dict[str, str]:
    statuses = {
        "insert": "SKIPPED",
        "read": "SKIPPED",
        "update": "SKIPPED",
        "cleanup": "SKIPPED",
        "final": "FAIL",
        "message": "",
    }

    if not has_supabase_env():
        statuses["final"] = "SKIPPED"
        statuses["message"] = (
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. "
            "Set both environment variables to run --execute."
        )
        return statuses

    client = None
    try:
        client = create_supabase_client()
        payload = build_test_payload()

        # Remove only a stale R41 test row for the exact test key before insert.
        cleanup_test_row(client)

        client.table(TABLE_NAME).insert(payload).execute()
        inserted_rows = select_test_rows(client)
        if not inserted_rows or inserted_rows[0].get("summary") != TEST_SUMMARY:
            statuses["insert"] = "FAIL"
            statuses["message"] = "Insert did not produce the expected test row."
            return statuses
        statuses["insert"] = "PASS"
        statuses["read"] = "PASS"

        (
            client.table(TABLE_NAME)
            .update({"summary": UPDATED_TEST_SUMMARY, "generated_at": TEST_GENERATED_AT})
            .eq("person_name", TEST_PERSON_NAME)
            .eq("week_start", TEST_WEEK_START)
            .execute()
        )
        updated_rows = select_test_rows(client)
        if not updated_rows or updated_rows[0].get("summary") != UPDATED_TEST_SUMMARY:
            statuses["update"] = "FAIL"
            statuses["message"] = "Update did not produce the expected test summary."
            return statuses
        statuses["update"] = "PASS"

        if cleanup_test_row(client):
            statuses["cleanup"] = "PASS"
            statuses["final"] = "PASS"
            statuses["message"] = "Insert, read back, update, and cleanup all completed."
        else:
            statuses["cleanup"] = "FAIL"
            statuses["message"] = "Cleanup did not remove the R41 test row."
        return statuses
    except Exception as exc:  # noqa: BLE001 - CLI should summarize any client failure safely.
        statuses["message"] = f"{type(exc).__name__}: {exc}"
        return statuses
    finally:
        if client is not None and statuses["cleanup"] != "PASS":
            try:
                if cleanup_test_row(client):
                    statuses["cleanup"] = "PASS"
            except Exception as exc:  # noqa: BLE001
                statuses["cleanup"] = "FAIL"
                if statuses["message"]:
                    statuses["message"] += f" Cleanup failed: {type(exc).__name__}: {exc}"
                else:
                    statuses["message"] = f"Cleanup failed: {type(exc).__name__}: {exc}"


def print_result(mode: str, statuses: dict[str, str]) -> None:
    print("R41 Supabase weekly report isolated write test")
    print(f"Mode: {mode}")
    print(f"Supabase key: {'present' if has_supabase_env() else 'missing'}")
    print(f"Test key: {TEST_PERSON_NAME} | {TEST_WEEK_START}")
    print(f"Insert: {statuses['insert']}")
    print(f"Read back: {statuses['read']}")
    print(f"Update: {statuses['update']}")
    print(f"Cleanup: {statuses['cleanup']}")
    print(f"Final status: {statuses['final']}")
    if statuses.get("message"):
        print(f"Message: {statuses['message']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an isolated Supabase weekly_reports write test for PGY90."
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate payload without connecting.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run insert/read/update/cleanup against Supabase using environment credentials.",
    )
    args = parser.parse_args()
    if args.dry_run and args.execute:
        parser.error("Use either --dry-run or --execute, not both.")
    return args


def main() -> int:
    args = parse_args()
    mode = "execute" if args.execute else "dry-run"
    statuses = run_execute() if args.execute else run_dry_run()
    print_result(mode, statuses)
    return 1 if statuses["final"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
