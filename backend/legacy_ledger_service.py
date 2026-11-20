"""Isolated Admin-only workspace for legacy spreadsheet sessions."""

import json
import secrets
from typing import Any, Dict, List, Optional

try:
    from backend import database
    from backend.audit_service import record_audit_event
    from backend.excel_service import recalculate_summary
except ImportError:
    import database
    from audit_service import record_audit_event
    from excel_service import recalculate_summary


def _require_admin(connection, admin_id: str) -> None:
    marker = database._placeholder()
    row = connection.execute(
        f"""
        SELECT r.name
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE u.id = {marker} AND u.is_active = 1
        """,
        (admin_id,),
    ).fetchone()
    if not row or row["name"] != "Admin":
        raise PermissionError("Only Admin users have access to the Legacy Ledger workspace.")


def import_session_to_legacy(admin_id: str, session_id: str) -> dict:
    """Import an existing prototype session into the isolated Legacy Ledger.
    
    Legacy rows are strictly isolated: they never populate active ledger_entries,
    never create petty_cash_requests, and never alter cash_account_balances.
    """
    marker = database._placeholder()
    timestamp = database.now_iso()
    legacy_id = secrets.token_urlsafe(18)

    with database.get_connection() as connection:
        _require_admin(connection, admin_id)

        # Check if already imported
        existing = connection.execute(
            f"SELECT * FROM legacy_ledger_sessions WHERE source_session_id = {marker}",
            (session_id,),
        ).fetchone()
        if existing:
            return get_legacy_session(existing["id"], admin_id)

        # Get session from legacy sessions table
        source = connection.execute(
            f"SELECT * FROM sessions WHERE id = {marker}",
            (session_id,),
        ).fetchone()
        if not source:
            raise LookupError(f"Source session '{session_id}' not found.")

        data = source["data"]
        if isinstance(data, str):
            data_dict = json.loads(data)
        else:
            data_dict = data

        payload = {
            "opening_balance": source["opening_balance"],
            "start_date": source["start_date"],
            "end_date": source["end_date"],
            "tx_count": source["tx_count"],
            "transactions": data_dict.get("transactions", []),
            "summary": data_dict.get("summary", {}),
            "source_excel_filename": data_dict.get("source_excel_filename") or source["name"],
        }

        connection.execute(
            f"""
            INSERT INTO legacy_ledger_sessions
                (id, source_session_id, name, source_filename,
                 imported_at, imported_by, data_json)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                legacy_id,
                session_id,
                source["name"],
                payload.get("source_excel_filename"),
                timestamp,
                admin_id,
                json.dumps(payload),
            ),
        )

        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="LEGACY_LEDGER_IMPORTED",
            entity_type="legacy_ledger_session",
            entity_id=legacy_id,
            after={
                "name": source["name"],
                "source_session_id": session_id,
                "tx_count": source["tx_count"],
            },
            correlation_id=legacy_id,
        )
        connection.commit()

    return get_legacy_session(legacy_id, admin_id)


def create_legacy_session(
    admin_id: str,
    name: str,
    opening_balance: float,
    start_date: str,
    end_date: str,
    transactions: list,
    summary: Optional[dict] = None,
    source_filename: Optional[str] = None,
) -> dict:
    """Create a new isolated legacy session."""
    clean_name = (name or "").strip()
    if not clean_name:
        clean_name = f"Legacy Ledger {start_date} - {end_date}"

    if summary is None:
        summary = recalculate_summary(
            opening_balance=opening_balance,
            start_date=start_date,
            end_date=end_date,
            transactions=transactions,
        )

    legacy_id = secrets.token_urlsafe(18)
    source_session_id = f"custom-legacy-{secrets.token_hex(8)}"
    timestamp = database.now_iso()
    marker = database._placeholder()

    payload = {
        "opening_balance": opening_balance,
        "start_date": start_date,
        "end_date": end_date,
        "tx_count": len(transactions),
        "transactions": transactions,
        "summary": summary,
        "source_excel_filename": source_filename,
    }

    with database.get_connection() as connection:
        _require_admin(connection, admin_id)
        connection.execute(
            f"""
            INSERT INTO legacy_ledger_sessions
                (id, source_session_id, name, source_filename,
                 imported_at, imported_by, data_json)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                legacy_id,
                source_session_id,
                clean_name,
                source_filename,
                timestamp,
                admin_id,
                json.dumps(payload),
            ),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="LEGACY_LEDGER_IMPORTED",
            entity_type="legacy_ledger_session",
            entity_id=legacy_id,
            after={"name": clean_name, "tx_count": len(transactions)},
            correlation_id=legacy_id,
        )
        connection.commit()

    return get_legacy_session(legacy_id, admin_id)


def list_legacy_sessions(admin_id: str) -> List[Dict[str, Any]]:
    """List all isolated legacy sessions for Admin."""
    marker = database._placeholder()
    with database.get_connection() as connection:
        _require_admin(connection, admin_id)
        rows = connection.execute(
            """
            SELECT l.id, l.source_session_id, l.name, l.source_filename,
                   l.imported_at, l.imported_by, u.username AS imported_by_username,
                   l.data_json
            FROM legacy_ledger_sessions l
            LEFT JOIN users u ON u.id = l.imported_by
            ORDER BY l.imported_at DESC
            """
        ).fetchall()

        results = []
        for r in rows:
            data = json.loads(r["data_json"])
            results.append({
                "id": r["id"],
                "source_session_id": r["source_session_id"],
                "name": r["name"],
                "source_filename": r["source_filename"],
                "imported_at": r["imported_at"],
                "imported_by": r["imported_by"],
                "imported_by_username": r["imported_by_username"],
                "opening_balance": data.get("opening_balance", 0.0),
                "start_date": data.get("start_date", ""),
                "end_date": data.get("end_date", ""),
                "tx_count": data.get("tx_count", len(data.get("transactions", []))),
                "is_legacy": True,
            })
        return results


def get_legacy_session(session_id: str, admin_id: str) -> dict:
    """Get full legacy session content with all rows and summary."""
    marker = database._placeholder()
    with database.get_connection() as connection:
        _require_admin(connection, admin_id)
        row = connection.execute(
            f"""
            SELECT l.id, l.source_session_id, l.name, l.source_filename,
                   l.imported_at, l.imported_by, u.username AS imported_by_username,
                   l.data_json
            FROM legacy_ledger_sessions l
            LEFT JOIN users u ON u.id = l.imported_by
            WHERE l.id = {marker}
            """,
            (session_id,),
        ).fetchone()
        if not row:
            raise LookupError("Legacy session not found.")

        data = json.loads(row["data_json"])
        return {
            "id": row["id"],
            "source_session_id": row["source_session_id"],
            "name": row["name"],
            "source_filename": row["source_filename"],
            "imported_at": row["imported_at"],
            "imported_by": row["imported_by"],
            "imported_by_username": row["imported_by_username"],
            "is_legacy": True,
            **data,
        }


def update_legacy_session(
    session_id: str,
    admin_id: str,
    transactions: list,
    opening_balance: Optional[float] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    """Update rows in an isolated legacy session without touching active ledger."""
    marker = database._placeholder()
    timestamp = database.now_iso()

    with database.get_connection() as connection:
        _require_admin(connection, admin_id)
        row = connection.execute(
            f"SELECT * FROM legacy_ledger_sessions WHERE id = {marker}",
            (session_id,),
        ).fetchone()
        if not row:
            raise LookupError("Legacy session not found.")

        data = json.loads(row["data_json"])
        new_opening = opening_balance if opening_balance is not None else data.get("opening_balance", 0.0)
        new_start = start_date if start_date is not None else data.get("start_date", "")
        new_end = end_date if end_date is not None else data.get("end_date", "")
        new_name = name.strip() if name and name.strip() else row["name"]

        new_summary = recalculate_summary(
            opening_balance=new_opening,
            start_date=new_start,
            end_date=new_end,
            transactions=transactions,
        )

        updated_payload = {
            "opening_balance": new_opening,
            "start_date": new_start,
            "end_date": new_end,
            "tx_count": len(transactions),
            "transactions": new_summary.get("transactions", transactions),
            "summary": new_summary,
            "source_excel_filename": data.get("source_excel_filename"),
        }

        connection.execute(
            f"""
            UPDATE legacy_ledger_sessions
            SET name = {marker}, data_json = {marker}
            WHERE id = {marker}
            """,
            (new_name, json.dumps(updated_payload), session_id),
        )

        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="LEGACY_LEDGER_UPDATED",
            entity_type="legacy_ledger_session",
            entity_id=session_id,
            before={"tx_count": data.get("tx_count", 0)},
            after={"tx_count": len(transactions), "name": new_name},
            correlation_id=session_id,
        )
        connection.commit()

    return get_legacy_session(session_id, admin_id)


def delete_legacy_session(session_id: str, admin_id: str) -> bool:
    """Delete an isolated legacy session."""
    marker = database._placeholder()
    with database.get_connection() as connection:
        _require_admin(connection, admin_id)
        cur = connection.execute(
            f"DELETE FROM legacy_ledger_sessions WHERE id = {marker}",
            (session_id,),
        )
        if cur.rowcount == 0:
            raise LookupError("Legacy session not found.")

        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="LEGACY_LEDGER_DELETED",
            entity_type="legacy_ledger_session",
            entity_id=session_id,
            correlation_id=session_id,
        )
        connection.commit()
        return True
