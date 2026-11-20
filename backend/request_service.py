"""Server-enforced petty cash request lifecycle."""

import secrets
from decimal import Decimal, InvalidOperation
from typing import Optional

try:
    from backend import database
    from backend.notification_service import create_notification
    from backend.audit_service import record_audit_event
except ImportError:
    import database
    from notification_service import create_notification
    from audit_service import record_audit_event


VALID_TRANSITIONS = {
    ("DRAFT", "SUBMITTED"),
    ("SUBMITTED", "APPROVED"),
    ("SUBMITTED", "DRAFT"),
    ("SUBMITTED", "REJECTED"),
}


def _amount(value) -> str:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("Amount must be a valid number.")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    return format(amount, "f")


def _master_record(connection, table: str, record_id: str) -> bool:
    marker = database._placeholder()
    return bool(
        connection.execute(
            f"SELECT id FROM {table} WHERE id={marker} AND is_active=1",
            (record_id,),
        ).fetchone()
    )


def _approved_assignment(connection, manager_id: str, employee_id: str) -> bool:
    marker = database._placeholder()
    return bool(
        connection.execute(
            f"""
            SELECT id FROM manager_employee_assignments
            WHERE manager_id={marker} AND employee_id={marker} AND status='APPROVED'
            """,
            (manager_id, employee_id),
        ).fetchone()
    )


def _record_status(connection, request_id: str, previous: Optional[str], target: str, actor: str, reason: Optional[str]):
    marker = database._placeholder()
    connection.execute(
        f"""
        INSERT INTO request_status_history
            (id, request_id, from_status, to_status, changed_by, reason, created_at)
        VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker})
        """,
        (
            secrets.token_urlsafe(18),
            request_id,
            previous,
            target,
            actor,
            reason,
            database.now_iso(),
        ),
    )


def create_draft(
    requester_id: str,
    project_id: str,
    ledger_id: str,
    category: str,
    request_date: str,
    amount,
    purpose: str,
    notes: Optional[str],
    approving_manager_id: str,
) -> dict:
    if requester_id == approving_manager_id:
        raise ValueError("A requester cannot approve their own request.")
    if not purpose.strip():
        raise ValueError("Purpose is required.")
    if not category.strip():
        raise ValueError("Category is required.")
    normalized_amount = _amount(amount)
    request_id = secrets.token_urlsafe(18)
    timestamp = database.now_iso()
    marker = database._placeholder()
    with database.get_connection() as connection:
        if not all(
            (
                _master_record(connection, "projects", project_id),
                _master_record(connection, "ledgers", ledger_id),
                _approved_assignment(connection, approving_manager_id, requester_id),
            )
        ):
            raise ValueError("Project, ledger, category, and approved Manager assignment are required.")
        connection.execute(
            f"""
            INSERT INTO petty_cash_requests
                (id, requester_id, approving_manager_id, project_id, ledger_id, category_id,
                 category_name, request_date, amount, purpose, notes, status, created_at, updated_at)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker},
                    {marker}, {marker}, {marker}, {marker}, {marker}, 'DRAFT', {marker}, {marker})
            """,
            (
                request_id,
                requester_id,
                approving_manager_id,
                project_id,
                ledger_id,
                "system-request-category",
                category.strip(),
                request_date,
                normalized_amount,
                purpose.strip(),
                notes.strip() if notes else None,
                timestamp,
                timestamp,
            ),
        )
        _record_status(connection, request_id, None, "DRAFT", requester_id, None)
        record_audit_event(
            connection=connection,
            actor_user_id=requester_id,
            action="PETTY_CASH_REQUEST_CREATED",
            entity_type="petty_cash_request",
            entity_id=request_id,
            after={
                "status": "DRAFT",
                "amount": normalized_amount,
                "project_id": project_id,
                "ledger_id": ledger_id,
                "category": category.strip(),
                "purpose": purpose.strip(),
            },
            correlation_id=request_id,
        )
        connection.commit()
    return get_request(request_id)


def update_draft(request_id: str, requester_id: str, values: dict) -> dict:
    allowed = {
        "project_id",
        "ledger_id",
        "category",
        "request_date",
        "amount",
        "purpose",
        "notes",
        "approving_manager_id",
    }
    if set(values) - allowed:
        raise ValueError("Only draft request fields can be updated.")
    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"SELECT * FROM petty_cash_requests WHERE id={marker} AND requester_id={marker}",
            (request_id, requester_id),
        ).fetchone()
        if not row:
            raise LookupError("Draft request not found.")
        if row["status"] != "DRAFT":
            raise ValueError("Only DRAFT requests can be edited.")
        merged = dict(row)
        merged.update(values)
        if merged["requester_id"] == merged["approving_manager_id"]:
            raise ValueError("A requester cannot approve their own request.")
        if not merged["purpose"].strip():
            raise ValueError("Purpose is required.")
        category = merged.get("category", merged["category_name"])
        if not category.strip():
            raise ValueError("Category is required.")
        if not all(
            (
                _master_record(connection, "projects", merged["project_id"]),
                _master_record(connection, "ledgers", merged["ledger_id"]),
                _approved_assignment(
                    connection, merged["approving_manager_id"], requester_id
                ),
            )
        ):
            raise ValueError("Project, ledger, category, and approved Manager assignment are required.")
        connection.execute(
            f"""
            UPDATE petty_cash_requests
            SET project_id={marker}, ledger_id={marker}, category_name={marker},
                request_date={marker}, amount={marker}, purpose={marker}, notes={marker},
                approving_manager_id={marker}, updated_at={marker}
            WHERE id={marker}
            """,
            (
                merged["project_id"],
                merged["ledger_id"],
                category.strip(),
                merged["request_date"],
                _amount(merged["amount"]),
                merged["purpose"].strip(),
                merged["notes"].strip() if merged["notes"] else None,
                merged["approving_manager_id"],
                database.now_iso(),
                request_id,
            ),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=requester_id,
            action="PETTY_CASH_REQUEST_UPDATED",
            entity_type="petty_cash_request",
            entity_id=request_id,
            before={
                "amount": str(row["amount"]),
                "purpose": row["purpose"],
                "project_id": row["project_id"],
                "ledger_id": row["ledger_id"],
            },
            after={
                "amount": _amount(merged["amount"]),
                "purpose": merged["purpose"].strip(),
                "project_id": merged["project_id"],
                "ledger_id": merged["ledger_id"],
            },
            correlation_id=request_id,
        )
        connection.commit()
    return get_request(request_id)


def submit_request(request_id: str, requester_id: str) -> dict:
    return _transition(request_id, requester_id, "SUBMITTED", None, "requester")


def manager_decision(
    request_id: str,
    manager_id: str,
    target: str,
    reason: Optional[str] = None,
) -> dict:
    if target in {"DRAFT", "REJECTED"} and not (reason or "").strip():
        raise ValueError("A reason is required for request changes or rejection.")
    return _transition(request_id, manager_id, target, reason, "manager")


def _transition(
    request_id: str,
    actor_id: str,
    target: str,
    reason: Optional[str],
    actor_type: str,
) -> dict:
    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"SELECT * FROM petty_cash_requests WHERE id={marker}",
            (request_id,),
        ).fetchone()
        if not row:
            raise LookupError("Request not found.")
        if (row["status"], target) not in VALID_TRANSITIONS:
            raise ValueError(f"Cannot transition request from {row['status']} to {target}.")
        if actor_type == "requester" and row["requester_id"] != actor_id:
            raise PermissionError("Only the requester can submit this request.")
        if actor_type == "manager" and (
            row["approving_manager_id"] != actor_id
            or not _approved_assignment(connection, actor_id, row["requester_id"])
        ):
            raise PermissionError("Only the approved Manager can review this request.")
        timestamp = database.now_iso()
        connection.execute(
            f"""
            UPDATE petty_cash_requests
            SET status={marker}, change_reason={marker}, rejection_reason={marker},
                submitted_at=CASE WHEN {marker}='SUBMITTED' THEN {marker} ELSE submitted_at END,
                approved_at=CASE WHEN {marker}='APPROVED' THEN {marker} ELSE approved_at END,
                updated_at={marker}
            WHERE id={marker}
            """,
            (
                target,
                reason if target == "DRAFT" else None,
                reason if target == "REJECTED" else None,
                target,
                timestamp,
                target,
                timestamp,
                timestamp,
                request_id,
            ),
        )
        _record_status(connection, request_id, row["status"], target, actor_id, reason)
        action_map = {
            "SUBMITTED": "PETTY_CASH_REQUEST_SUBMITTED",
            "APPROVED": "PETTY_CASH_REQUEST_APPROVED",
            "DRAFT": "PETTY_CASH_REQUEST_CHANGES_REQUESTED",
            "REJECTED": "PETTY_CASH_REQUEST_REJECTED",
        }
        record_audit_event(
            connection=connection,
            actor_user_id=actor_id,
            action=action_map.get(target, f"PETTY_CASH_REQUEST_{target}"),
            entity_type="petty_cash_request",
            entity_id=request_id,
            before={"status": row["status"]},
            after={"status": target, "reason": reason},
            correlation_id=request_id,
        )
        connection.commit()

    with database.get_connection() as connection:
        requester_info = connection.execute(
            f"SELECT username FROM users WHERE id={database._placeholder()}",
            (row["requester_id"],),
        ).fetchone()
        manager_info = connection.execute(
            f"SELECT username FROM users WHERE id={database._placeholder()}",
            (row["approving_manager_id"],),
        ).fetchone()
    requester_name = requester_info["username"] if requester_info else "Employee"
    manager_name = manager_info["username"] if manager_info else "Manager"
    amt_str = f"₹{Decimal(str(row['amount'])).quantize(Decimal('0.01'))}"
    purpose_str = row["purpose"] or "Petty cash expense"

    if target == "SUBMITTED":
        create_notification(
            row["approving_manager_id"],
            "REQUEST_SUBMITTED",
            f"Petty cash request submitted by {requester_name}",
            f"Request for {amt_str} ({purpose_str}) submitted by {requester_name} is awaiting your approval.",
            "petty_cash_request",
            request_id,
        )
    elif target == "APPROVED":
        create_notification(
            row["requester_id"],
            "REQUEST_APPROVED",
            f"Petty cash request approved by {manager_name}",
            f"Your request for {amt_str} ({purpose_str}) was approved by Manager {manager_name}. Please upload voucher receipts and submit for posting.",
            "petty_cash_request",
            request_id,
        )
    elif target == "DRAFT":
        create_notification(
            row["requester_id"],
            "REQUEST_DRAFT",
            f"Changes requested by Manager {manager_name}",
            f"Manager {manager_name} returned your request for {amt_str} for corrections: {reason}",
            "petty_cash_request",
            request_id,
        )
    elif target == "REJECTED":
        create_notification(
            row["requester_id"],
            "REQUEST_REJECTED",
            f"Petty cash request rejected by {manager_name}",
            f"Manager {manager_name} rejected your request for {amt_str} ({purpose_str}). Reason: {reason}",
            "petty_cash_request",
            request_id,
        )
    return get_request(request_id)


def get_request(request_id: str) -> dict:
    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT r.*, p.name AS project_name, l.name AS ledger_name,
                   u.username AS requester_username, m.username AS manager_username
            FROM petty_cash_requests r
            JOIN projects p ON p.id=r.project_id
            JOIN ledgers l ON l.id=r.ledger_id
            JOIN users u ON u.id=r.requester_id
            JOIN users m ON m.id=r.approving_manager_id
            WHERE r.id={marker}
            """,
            (request_id,),
        ).fetchone()
        if not row:
            raise LookupError("Request not found.")
        result = dict(row)
        history = connection.execute(
            f"""
            SELECT from_status, to_status, changed_by, reason, created_at
            FROM request_status_history WHERE request_id={marker}
            ORDER BY created_at ASC
            """,
            (request_id,),
        ).fetchall()
        audit_events = connection.execute(
            f"""
            SELECT action, actor_user_id, before_json, after_json, correlation_id, created_at
            FROM audit_events
            WHERE entity_type='petty_cash_request' AND entity_id={marker}
            ORDER BY created_at ASC
            """,
            (request_id,),
        ).fetchall()
    result["history"] = [dict(item) for item in history]
    result["audit_events"] = [dict(item) for item in audit_events]
    return result


def list_requests(
    user_id: str,
    role: str,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[dict]:
    marker = database._placeholder()
    if role == "Employee":
        clause, params = f"WHERE r.requester_id={marker}", [user_id]
    elif role == "Manager":
        clause, params = f"WHERE r.approving_manager_id={marker}", [user_id]
    else:
        clause, params = "", []
    pagination_clause = ""
    if limit is not None and limit > 0:
        pagination_clause = f"LIMIT {marker} OFFSET {marker}"
        params.extend([limit, max(0, offset)])
    with database.get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT r.id, r.request_date, r.amount, r.purpose, r.status,
                   r.requester_id, r.approving_manager_id,
                   p.name AS project_name, l.name AS ledger_name, r.category_name
            FROM petty_cash_requests r
            JOIN projects p ON p.id=r.project_id
            JOIN ledgers l ON l.id=r.ledger_id
            {clause}
            ORDER BY r.created_at DESC
            {pagination_clause}
            """,
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]

