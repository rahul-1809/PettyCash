"""
Session persistence for PettyCash Pro.

Set DATABASE_URL to use Supabase PostgreSQL in production. Without it, local
development falls back to the existing SQLite database.
"""

import atexit
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional

try:
    from pathlib import Path
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=True)
except ImportError:
    pass

try:
    from backend.migration_runner import apply_migrations
except ImportError:
    from migration_runner import apply_migrations

DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sessions.db",
)

if DATABASE_URL:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "DATABASE_URL is set, but psycopg is not installed. "
            "Install the backend requirements."
        ) from exc

_POOL = None


def get_pool():
    global _POOL
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"):
        return None
    if DATABASE_URL and _POOL is None:
        try:
            from psycopg_pool import ConnectionPool
            _POOL = ConnectionPool(
                DATABASE_URL,
                min_size=2,
                max_size=12,
                timeout=10.0,
                max_idle=300.0,
                kwargs={"row_factory": dict_row},
                open=True,
            )
        except Exception:
            _POOL = None
    return _POOL


def close_pool():
    global _POOL
    if _POOL is not None:
        try:
            _POOL.close()
        except Exception:
            pass
        _POOL = None


atexit.register(close_pool)


def get_connection():
    if DATABASE_URL:
        pool = get_pool()
        if pool is not None:
            return pool.connection()
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _placeholder() -> str:
    return "%s" if DATABASE_URL else "?"


def init_db():
    """Create persistence tables and seed global projects from existing sessions."""
    data_type = "JSONB" if DATABASE_URL else "TEXT"
    with get_connection() as conn:
        apply_migrations(conn)
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                opening_balance REAL NOT NULL DEFAULT 0,
                start_date  TEXT NOT NULL DEFAULT '',
                end_date    TEXT NOT NULL DEFAULT '',
                tx_count   INTEGER NOT NULL DEFAULT 0,
                data       {data_type} NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_categories (
                name       TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    seed_system_roles()
    _seed_project_categories()


def seed_system_roles():
    roles = (
        ("role-admin", "Admin"),
        ("role-manager", "Manager"),
        ("role-employee", "Employee"),
    )
    marker = _placeholder()
    with get_connection() as conn:
        for role_id, name in roles:
            conn.execute(
                f"""
                INSERT INTO roles (id, name, created_at)
                VALUES ({marker}, {marker}, {marker})
                ON CONFLICT (name) DO NOTHING
                """,
                (role_id, name, now_iso()),
            )
        conn.execute(
            f"""
            INSERT INTO categories (id, name, is_active, created_at, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
            ON CONFLICT (id) DO NOTHING
            """,
            ("system-request-category", "__request_category__", 1, now_iso(), now_iso()),
        )
        conn.execute(
            f"""
            INSERT INTO cash_accounts
                (id, name, currency, opening_balance, minimum_balance, is_active, created_at, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker})
            ON CONFLICT (id) DO NOTHING
            """,
            (
                "system-main-cash",
                "Main Petty Cash",
                "INR",
                "0.00",
                "0.00",
                1,
                now_iso(),
                now_iso(),
            ),
        )
        conn.execute(
            f"""
            INSERT INTO cash_account_balances
                (cash_account_id, current_balance, version, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker})
            ON CONFLICT (cash_account_id) DO NOTHING
            """,
            ("system-main-cash", "0.00", 1, now_iso()),
        )
        conn.commit()


def _seed_project_categories():
    with get_connection() as conn:
        rows = conn.execute("SELECT data FROM sessions").fetchall()
        existing = {
            row["name"] for row in conn.execute(
                "SELECT name FROM project_categories"
            ).fetchall()
        }
        projects = set(existing)
        for row in rows:
            data = row["data"]
            if isinstance(data, str):
                data = json.loads(data)
            for transaction in data.get("transactions", []):
                project = str(transaction.get("project") or "").strip()
                if project:
                    projects.add(project)
        for project in projects - existing:
            marker = _placeholder()
            conn.execute(
                f"INSERT INTO project_categories (name, created_at) "
                f"VALUES ({marker}, {marker})",
                (project, now_iso()),
            )
        conn.commit()


def list_project_categories() -> List[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name FROM project_categories ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]


def add_project_category(name: str) -> str:
    project = name.strip()
    if not project:
        return ""
    marker = _placeholder()
    with get_connection() as conn:
        existing = conn.execute(
            f"SELECT name FROM project_categories WHERE name={marker}",
            (project,),
        ).fetchone()
        if not existing:
            conn.execute(
                f"INSERT INTO project_categories (name, created_at) "
                f"VALUES ({marker}, {marker})",
                (project, now_iso()),
            )
            conn.commit()
    return project


def add_project_categories(names: List[str]):
    for name in names:
        add_project_category(name)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_sessions() -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, updated_at, opening_balance, "
            "start_date, end_date, tx_count FROM sessions "
            "ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def create_session(
    name: str,
    opening_balance: float,
    start_date: str,
    end_date: str,
    transactions: list,
    summary: dict,
    source_excel_base64: Optional[str] = None,
    source_excel_filename: Optional[str] = None,
) -> dict:
    session_id = str(uuid.uuid4())
    ts = now_iso()
    tx_count = len(transactions)
    data_blob = {
        "transactions": transactions,
        "summary": summary,
        "source_excel_base64": source_excel_base64,
        "source_excel_filename": source_excel_filename,
    }
    marker = _placeholder()

    with get_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO sessions
                (id, name, created_at, updated_at, opening_balance,
                 start_date, end_date, tx_count, data)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker},
                    {marker}, {marker}, {marker}, {marker})
            """,
            (
                session_id,
                name,
                ts,
                ts,
                opening_balance,
                start_date,
                end_date,
                tx_count,
                json.dumps(data_blob),
            ),
        )
        conn.commit()
    return get_session(session_id)


def get_session(session_id: str) -> Optional[dict]:
    marker = _placeholder()
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT * FROM sessions WHERE id = {marker}", (session_id,)
        ).fetchone()
        if not row:
            return None

        data = dict(row)
        if isinstance(data["data"], str):
            data["data"] = json.loads(data["data"])
        return data


def update_session(
    session_id: str,
    opening_balance: float,
    start_date: str,
    end_date: str,
    transactions: list,
    summary: dict,
    name: Optional[str] = None,
    source_excel_base64: Optional[str] = None,
    source_excel_filename: Optional[str] = None,
) -> Optional[dict]:
    ts = now_iso()
    tx_count = len(transactions)
    data_blob = {
        "transactions": transactions,
        "summary": summary,
        "source_excel_base64": source_excel_base64,
        "source_excel_filename": source_excel_filename,
    }
    marker = _placeholder()
    values = [
        ts,
        opening_balance,
        start_date,
        end_date,
        tx_count,
        json.dumps(data_blob),
    ]

    if name is not None:
        query = (
            f"UPDATE sessions SET updated_at={marker}, "
            f"opening_balance={marker}, start_date={marker}, end_date={marker}, "
            f"tx_count={marker}, data={marker}, name={marker} "
            f"WHERE id={marker}"
        )
        values.extend([name, session_id])
    else:
        query = (
            f"UPDATE sessions SET updated_at={marker}, "
            f"opening_balance={marker}, start_date={marker}, end_date={marker}, "
            f"tx_count={marker}, data={marker} WHERE id={marker}"
        )
        values.append(session_id)

    with get_connection() as conn:
        conn.execute(query, values)
        conn.commit()
    return get_session(session_id)


def rename_session(session_id: str, new_name: str) -> Optional[dict]:
    marker = _placeholder()
    with get_connection() as conn:
        conn.execute(
            f"UPDATE sessions SET name={marker}, updated_at={marker} "
            f"WHERE id={marker}",
            (new_name, now_iso(), session_id),
        )
        conn.commit()
    return get_session(session_id)


def delete_session(session_id: str) -> bool:
    marker = _placeholder()
    with get_connection() as conn:
        cur = conn.execute(
            f"DELETE FROM sessions WHERE id={marker}", (session_id,)
        )
        conn.commit()
        return cur.rowcount > 0
