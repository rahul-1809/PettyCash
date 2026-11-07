"""
Session persistence for PettyCash Pro.

Set DATABASE_URL to use Supabase PostgreSQL in production. Without it, local
development falls back to the existing SQLite database.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional

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


def get_connection():
    if DATABASE_URL:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _placeholder() -> str:
    return "%s" if DATABASE_URL else "?"


def init_db():
    """Create the sessions table in the configured database."""
    data_type = "JSONB" if DATABASE_URL else "TEXT"
    with get_connection() as conn:
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
        conn.commit()


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
