"""Small, idempotent SQL migration runner for the current persistence layer."""

from pathlib import Path
from typing import Any
from datetime import datetime, timezone


DEFAULT_MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def apply_migrations(connection: Any, migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> None:
    """Apply pending SQL migrations using an existing database connection."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )

    applied = set()
    for row in connection.execute("SELECT version FROM schema_migrations").fetchall():
        applied.add(row["version"] if hasattr(row, "keys") else row[0])

    for migration_path in sorted(migrations_dir.glob("*.sql")):
        version = migration_path.stem
        if version in applied:
            continue

        migration_sql = migration_path.read_text(encoding="utf-8")
        if connection.__class__.__module__.startswith("sqlite3"):
            connection.executescript(migration_sql)
        else:
            connection.execute(migration_sql)
        marker = "%s" if connection.__class__.__module__.startswith("psycopg") else "?"

        connection.execute(
            f"INSERT INTO schema_migrations (version, applied_at) VALUES ({marker}, {marker})",
            (
                version,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        )

