"""Immutable audit logging service."""

import json
import secrets
from typing import Any, Dict, List, Optional

try:
    from backend import database
    from backend.observability import get_correlation_id
except ImportError:
    import database
    try:
        from observability import get_correlation_id
    except ImportError:
        def get_correlation_id() -> str:
            return ""


def record_audit_event(
    connection=None,
    actor_user_id: Optional[str] = None,
    action: str = "",
    entity_type: str = "",
    entity_id: Optional[str] = None,
    before: Optional[Any] = None,
    after: Optional[Any] = None,
    correlation_id: Optional[str] = None,
) -> dict:
    """Record an immutable audit event.
    
    If an existing connection is provided, the record is inserted within
    that transaction so that it commits or rolls back atomically.
    Otherwise, a new connection is used and committed immediately.
    """
    event_id = secrets.token_urlsafe(18)
    corr_id = correlation_id or get_correlation_id() or secrets.token_urlsafe(18)
    timestamp = database.now_iso()
    before_json = json.dumps(before) if before is not None else None
    after_json = json.dumps(after) if after is not None else None
    marker = database._placeholder()

    query = f"""
        INSERT INTO audit_events
            (id, actor_user_id, action, entity_type, entity_id,
             before_json, after_json, correlation_id, created_at)
        VALUES ({marker}, {marker}, {marker}, {marker}, {marker},
                {marker}, {marker}, {marker}, {marker})
    """
    params = (
        event_id,
        actor_user_id,
        action,
        entity_type,
        entity_id,
        before_json,
        after_json,
        corr_id,
        timestamp,
    )

    if connection is not None:
        connection.execute(query, params)
    else:
        with database.get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    return {
        "id": event_id,
        "actor_user_id": actor_user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before_json": before_json,
        "after_json": after_json,
        "correlation_id": corr_id,
        "created_at": timestamp,
    }


def list_audit_events(
    actor_user_id: Optional[str] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List audit events with optional filtering, newest first."""
    clauses = []
    params = []
    marker = database._placeholder()

    if actor_user_id:
        clauses.append(f"a.actor_user_id = {marker}")
        params.append(actor_user_id)
    if action:
        clauses.append(f"a.action = {marker}")
        params.append(action)
    if entity_type:
        clauses.append(f"a.entity_type = {marker}")
        params.append(entity_type)
    if entity_id:
        clauses.append(f"a.entity_id = {marker}")
        params.append(entity_id)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    query = f"""
        SELECT a.id, a.actor_user_id, u.username AS actor_username,
               a.action, a.entity_type, a.entity_id,
               a.before_json, a.after_json, a.correlation_id, a.created_at
        FROM audit_events a
        LEFT JOIN users u ON u.id = a.actor_user_id
        {where_sql}
        ORDER BY a.created_at DESC
        LIMIT {limit} OFFSET {offset}
    """

    with database.get_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            result.append(d)
        return result


def get_audit_event(event_id: str) -> Optional[Dict[str, Any]]:
    """Get single audit event by id."""
    marker = database._placeholder()
    query = f"""
        SELECT a.id, a.actor_user_id, u.username AS actor_username,
               a.action, a.entity_type, a.entity_id,
               a.before_json, a.after_json, a.correlation_id, a.created_at
        FROM audit_events a
        LEFT JOIN users u ON u.id = a.actor_user_id
        WHERE a.id = {marker}
    """
    with database.get_connection() as connection:
        row = connection.execute(query, (event_id,)).fetchone()
        return dict(row) if row else None
