#!/usr/bin/env python3
"""Smoke-test the PGY90 DB adapter draft without writing data."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db_adapter import CORE_TABLES, get_db_adapter, get_db_backend_name


def main() -> int:
    backend = get_db_backend_name()
    print(f"PGY90 DB adapter smoke test")
    print(f"Backend: {backend}")

    try:
        adapter = get_db_adapter(backend)
        counts = adapter.table_counts()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Row counts:")
    for table_name in CORE_TABLES:
        print(f"- {table_name}: {counts.get(table_name, 0)}")

    print("Sample read:")
    people = adapter.list_people()
    print(f"- people sample rows: {min(len(people), 3)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
