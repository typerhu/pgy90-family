#!/usr/bin/env python3
"""Create a read-only SQLite backup and CSV export for PGY90 migration."""

from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


CORE_TABLES = [
    "people",
    "app_users",
    "daily_logs",
    "meal_logs",
    "coach_profiles",
    "weekly_reports",
]
LEGACY_TABLE = "coach_profile"


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "data" / "health.db"
BACKUP_DIR = ROOT_DIR / "backups"
EXPORT_DIR = ROOT_DIR / "exports"


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def export_table_csv(conn: sqlite3.Connection, table_name: str, output_path: Path) -> int:
    cursor = conn.execute(f"SELECT * FROM {quote_identifier(table_name)}")
    columns = [description[0] for description in cursor.description or []]
    rows = cursor.fetchall()

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(columns)
        writer.writerows(rows)

    return len(rows)


def export_schema(conn: sqlite3.Connection, output_path: Path) -> None:
    rows = conn.execute(
        """
        SELECT type, name, sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
          AND type IN ('table', 'index', 'trigger', 'view')
        ORDER BY type, name
        """
    ).fetchall()

    lines = [
        "-- PGY90 Health Coach SQLite schema export",
        f"-- Exported at: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    for _, _, sql in rows:
        lines.append(sql.rstrip(";") + ";")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_summary(
    summary_path: Path,
    export_time: datetime,
    backup_path: Path,
    schema_path: Path,
    exported_tables: list[tuple[str, int, Path]],
    missing_tables: list[str],
) -> None:
    lines = [
        "PGY90 SQLite Export Summary",
        "=" * 32,
        f"Export time: {export_time.isoformat(timespec='seconds')}",
        f"DB path: {DB_PATH}",
        f"Backup path: {backup_path}",
        f"Schema path: {schema_path}",
        "",
        "Exported tables:",
    ]

    if exported_tables:
        for table_name, count, output_path in exported_tables:
            lines.append(f"- {table_name}: {count} rows -> {output_path}")
    else:
        lines.append("- None")

    lines.extend(["", "Missing tables:"])
    if missing_tables:
        for table_name in missing_tables:
            lines.append(f"- {table_name}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "Privacy reminder:",
            "- CSV files and database backups may contain personal health data.",
            "- Do not commit backups/ or exports/ to GitHub.",
            "- Keep data/health.db out of GitHub.",
        ]
    )

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not DB_PATH.exists():
        print(
            f"ERROR: SQLite database not found at {DB_PATH}. "
            "No backup or export was created.",
            file=sys.stderr,
        )
        return 1

    export_time = datetime.now()
    timestamp = export_time.strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"health_backup_{timestamp}.db"
    schema_path = EXPORT_DIR / "schema.sql"
    summary_path = EXPORT_DIR / "export_summary.txt"

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(DB_PATH, backup_path)

    exported_tables: list[tuple[str, int, Path]] = []
    missing_tables: list[str] = []

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        export_schema(conn, schema_path)

        for table_name in CORE_TABLES:
            if not table_exists(conn, table_name):
                missing_tables.append(table_name)
                continue
            output_path = EXPORT_DIR / f"{table_name}.csv"
            count = export_table_csv(conn, table_name, output_path)
            exported_tables.append((table_name, count, output_path))

        if table_exists(conn, LEGACY_TABLE):
            output_path = EXPORT_DIR / "coach_profile_legacy.csv"
            count = export_table_csv(conn, LEGACY_TABLE, output_path)
            exported_tables.append((LEGACY_TABLE, count, output_path))
        else:
            missing_tables.append(LEGACY_TABLE)
    finally:
        conn.close()

    write_summary(
        summary_path,
        export_time,
        backup_path,
        schema_path,
        exported_tables,
        missing_tables,
    )

    print("PGY90 SQLite export completed.")
    print("Backup:")
    print(f"- {backup_path.relative_to(ROOT_DIR)}")
    print("Schema:")
    print(f"- {schema_path.relative_to(ROOT_DIR)}")
    print("CSV exports:")
    for table_name, count, output_path in exported_tables:
        print(f"- {table_name}: {count} rows -> {output_path.relative_to(ROOT_DIR)}")
    if missing_tables:
        print("Missing tables:")
        for table_name in missing_tables:
            print(f"- {table_name}")
    print("Summary:")
    print(f"- {summary_path.relative_to(ROOT_DIR)}")
    print("Reminder:")
    print("Do not commit backups/ or exports/ because they may contain personal health data.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
