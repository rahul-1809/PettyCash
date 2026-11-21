"""Persistence helpers for the normalized Phase 1 domain foundation."""

import uuid
from typing import Optional

try:
    from backend import database
    from backend.audit_service import record_audit_event
except ImportError:
    import database
    from audit_service import record_audit_event


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return database.now_iso()


def create_role(name: str) -> dict:
    role_id = _new_id()
    normalized_name = name.strip()
    with database.get_connection() as connection:
        marker = database._placeholder()
        existing = connection.execute(
            f"SELECT id, name FROM roles WHERE name={marker}",
            (normalized_name,),
        ).fetchone()
        if existing:
            return dict(existing)
        connection.execute(
            f"INSERT INTO roles (id, name, created_at) VALUES ({marker}, {marker}, {marker})",
            (role_id, normalized_name, _now()),
        )
        connection.commit()
    return {"id": role_id, "name": normalized_name}


def create_user(username: str, email: str, role_id: str) -> dict:
    user_id = _new_id()
    timestamp = _now()
    with database.get_connection() as connection:
        marker = database._placeholder()
        connection.execute(
            f"""
            INSERT INTO users
                (id, username, email, role_id, is_active, created_at, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (user_id, username.strip(), email.strip().lower(), role_id, 1, timestamp, timestamp),
        )
        connection.commit()
    return {"id": user_id, "username": username.strip(), "email": email.strip().lower()}


def create_master_record(table: str, name: str, actor_id: Optional[str] = None) -> dict:
    """Create a named Project, Ledger, or Category record."""
    if table not in {"projects", "ledgers", "categories"}:
        raise ValueError(f"Unsupported master-data table: {table}")

    record_id = _new_id()
    timestamp = _now()
    with database.get_connection() as connection:
        marker = database._placeholder()
        connection.execute(
            f"""
            INSERT INTO {table}
                (id, name, is_active, created_at, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (record_id, name.strip(), 1, timestamp, timestamp),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=actor_id,
            action=f"{table[:-1].upper()}_CREATED",
            entity_type=table[:-1],
            entity_id=record_id,
            after={"id": record_id, "name": name.strip(), "is_active": True},
        )
        connection.commit()
    return {"id": record_id, "name": name.strip()}


def list_master_records(table: str) -> list[dict]:
    if table not in {"projects", "ledgers", "categories"}:
        raise ValueError(f"Unsupported master-data table: {table}")
    with database.get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT id, name, is_active, created_at, updated_at
            FROM {table}
            ORDER BY name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def set_master_record_active(table: str, record_id: str, is_active: bool, actor_id: Optional[str] = None) -> bool:
    if table not in {"projects", "ledgers", "categories"}:
        raise ValueError(f"Unsupported master-data table: {table}")
    marker = database._placeholder()
    with database.get_connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE {table}
            SET is_active={marker}, updated_at={marker}
            WHERE id={marker}
            """,
            (int(is_active), _now(), record_id),
        )
        if cursor.rowcount == 1:
            record_audit_event(
                connection=connection,
                actor_user_id=actor_id,
                action=f"{table[:-1].upper()}_{'ACTIVATED' if is_active else 'DEACTIVATED'}",
                entity_type=table[:-1],
                entity_id=record_id,
                after={"is_active": bool(is_active)},
            )
        connection.commit()
        return cursor.rowcount == 1


def delete_master_record(table: str, record_id: str, actor_id: Optional[str] = None) -> dict:
    if table not in {"projects", "ledgers", "categories"}:
        raise ValueError(f"Unsupported master-data table: {table}")
    marker = database._placeholder()
    with database.get_connection() as connection:
        record = connection.execute(
            f"SELECT id, name FROM {table} WHERE id={marker}",
            (record_id,),
        ).fetchone()
        if not record:
            raise LookupError(f"{table[:-1].capitalize()} not found.")

        ref_field = "project_id" if table == "projects" else "ledger_id"
        usage_row = connection.execute(
            f"SELECT COUNT(*) FROM petty_cash_requests WHERE {ref_field}={marker}",
            (record_id,),
        ).fetchone()
        usage = (
            usage_row["count"] if isinstance(usage_row, dict) and "count" in usage_row
            else (next(iter(usage_row.values())) if isinstance(usage_row, dict) else (usage_row[0] if usage_row else 0))
        )
        if usage > 0:
            raise ValueError(
                f"Cannot permanently delete '{record['name']}' because it is linked to {usage} existing transaction request(s). "
                f"You can deactivate it instead so it is no longer selectable in new requests."
            )
        connection.execute(
            f"DELETE FROM {table} WHERE id={marker}",
            (record_id,),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=actor_id,
            action=f"{table[:-1].upper()}_DELETED",
            entity_type=table[:-1],
            entity_id=record_id,
            before={"id": record_id, "name": record["name"]},
        )
        connection.commit()
    return {"id": record_id, "name": record["name"], "deleted": True}


def create_cash_account(
    name: str,
    opening_balance: str = "0.00",
    minimum_balance: str = "0.00",
) -> dict:
    account_id = _new_id()
    timestamp = _now()
    with database.get_connection() as connection:
        marker = database._placeholder()
        connection.execute(
            f"""
            INSERT INTO cash_accounts
                (id, name, opening_balance, minimum_balance, created_at, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (account_id, name.strip(), opening_balance, minimum_balance, timestamp, timestamp),
        )
        connection.execute(
            f"""
            INSERT INTO cash_account_balances
                (cash_account_id, current_balance, version, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker})
            """,
            (account_id, opening_balance, 1, timestamp),
        )
        connection.commit()
    return {"id": account_id, "name": name.strip(), "opening_balance": opening_balance}


def get_cash_account_balance(account_id: str) -> Optional[dict]:
    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT cash_account_id, current_balance, version, updated_at
            FROM cash_account_balances
            WHERE cash_account_id = {marker}
            """,
            (account_id,),
        ).fetchone()
    return dict(row) if row else None


def list_cash_accounts() -> list[dict]:
    with database.get_connection() as connection:
        rows = connection.execute(
            """
            SELECT a.id, a.name, a.currency, a.opening_balance,
                   a.minimum_balance, a.is_active,
                   b.current_balance, b.version, a.created_at, a.updated_at
            FROM cash_accounts a
            JOIN cash_account_balances b ON b.cash_account_id=a.id
            ORDER BY a.name
            """
        ).fetchall()
    return [dict(row) for row in rows]
