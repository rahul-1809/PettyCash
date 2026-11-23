"""Atomic company cash receipt posting."""

import hashlib
import json
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

try:
    from backend import database
    from backend.notification_service import create_notification
    from backend.financial_control_service import validate_date_not_in_closed_period
    from backend.report_service import invalidate_report_cache
except ImportError:
    import database
    from notification_service import create_notification
    from financial_control_service import validate_date_not_in_closed_period
    from report_service import invalidate_report_cache


def _amount(value) -> str:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Receipt amount must be a valid number.") from exc
    if amount <= 0:
        raise ValueError("Receipt amount must be greater than zero.")
    return format(amount, "f")


def _date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Receipt date must be a valid ISO date.") from exc
    return value


def _require_admin(connection, admin_id: str) -> None:
    marker = database._placeholder()
    row = connection.execute(
        f"""
        SELECT r.name
        FROM users u
        JOIN roles r ON r.id=u.role_id
        WHERE u.id={marker} AND u.is_active=1
        """,
        (admin_id,),
    ).fetchone()
    if not row or row["name"] != "Admin":
        raise PermissionError("Only Admin users can create company receipts.")


def _active_record(connection, table: str, record_id: str) -> bool:
    marker = database._placeholder()
    row = connection.execute(
        f"SELECT id FROM {table} WHERE id={marker} AND is_active=1",
        (record_id,),
    ).fetchone()
    return bool(row)


def create_company_receipt(
    admin_id: str,
    amount,
    receipt_date: str,
    description: str,
    ledger_id: Optional[str] = None,
    category: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict:
    normalized_amount = _amount(amount)
    normalized_date = _date(receipt_date)
    description = (description or "").strip()
    ledger_id = (ledger_id or "").strip()
    category = (category or "").strip() or "Cash replenishment"
    project_id = (project_id or "").strip()

    if not description:
        raise ValueError("Receipt description is required.")

    marker = database._placeholder()
    timestamp = database.now_iso()
    cash_account_id = "system-main-cash"

    with database.get_connection() as connection:
        _require_admin(connection, admin_id)
        validate_date_not_in_closed_period(connection, normalized_date)

        # Resolve or validate project_id
        if not project_id:
            first_project = connection.execute("SELECT id FROM projects WHERE is_active=1 ORDER BY name LIMIT 1").fetchone()
            if first_project:
                project_id = first_project["id"]
            else:
                project_id = secrets.token_urlsafe(18)
                connection.execute(
                    f"INSERT INTO projects (id, name, is_active, created_at, updated_at) VALUES ({marker}, 'Petty Cash HQ', 1, {marker}, {marker})",
                    (project_id, timestamp, timestamp),
                )
        elif not _active_record(connection, "projects", project_id):
            raise ValueError("Selected project is invalid or inactive.")

        # Resolve or validate ledger_id
        if not ledger_id:
            first_ledger = connection.execute("SELECT id FROM ledgers WHERE is_active=1 ORDER BY name LIMIT 1").fetchone()
            if first_ledger:
                ledger_id = first_ledger["id"]
            else:
                ledger_id = secrets.token_urlsafe(18)
                connection.execute(
                    f"INSERT INTO ledgers (id, name, is_active, created_at, updated_at) VALUES ({marker}, 'Petty Cash', 1, {marker}, {marker})",
                    (ledger_id, timestamp, timestamp),
                )
        elif not _active_record(connection, "ledgers", ledger_id):
            raise ValueError("Selected ledger is invalid or inactive.")

        fingerprint_payload = "|".join((
            normalized_amount,
            normalized_date,
            description,
            ledger_id,
            category,
            project_id,
        ))
        idempotency_key = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()

        existing = connection.execute(
            f"SELECT * FROM company_receipts WHERE idempotency_key={marker}",
            (idempotency_key,),
        ).fetchone()
        if existing:
            entry = connection.execute(
                f"SELECT id FROM ledger_entries WHERE company_receipt_id={marker}",
                (existing["id"],),
            ).fetchone()
            return {
                "id": existing["id"],
                "amount": str(existing["amount"]),
                "receipt_date": existing["receipt_date"],
                "description": existing["description"],
                "ledger_id": existing["ledger_id"],
                "category": existing["category_name"],
                "project_id": existing["project_id"],
                "receipt_reference": existing["receipt_reference"],
                "ledger_entry_id": entry["id"] if entry else None,
                "duplicate": True,
            }

        balance = connection.execute(
            f"""
            SELECT current_balance, version
            FROM cash_account_balances
            WHERE cash_account_id={marker}
            """,
            (cash_account_id,),
        ).fetchone()
        if not balance:
            raise ValueError("Main petty cash balance is not configured.")

        receipt_id = secrets.token_urlsafe(18)
        entry_id = secrets.token_urlsafe(18)
        receipt_reference = f"RCPT-{normalized_date.replace('-', '')}-{secrets.token_hex(4).upper()}"
        current_balance = Decimal(str(balance["current_balance"]))
        receipt_amount = Decimal(normalized_amount)

        try:
            connection.execute(
                f"""
                INSERT INTO company_receipts
                    (id, cash_account_id, amount, receipt_date, description,
                     receipt_reference, idempotency_key, created_by, created_at,
                     project_id, ledger_id, category_name)
                VALUES ({marker}, {marker}, {marker}, {marker}, {marker},
                        {marker}, {marker}, {marker}, {marker}, {marker},
                        {marker}, {marker})
                """,
                (
                    receipt_id,
                    cash_account_id,
                    normalized_amount,
                    normalized_date,
                    description,
                    receipt_reference,
                    idempotency_key,
                    admin_id,
                    timestamp,
                    project_id,
                    ledger_id,
                    category,
                ),
            )
            connection.execute(
                f"""
                INSERT INTO ledger_entries
                    (id, cash_account_id, company_receipt_id, entry_type,
                     effective_date, amount, description, created_at)
                VALUES ({marker}, {marker}, {marker}, 'RECEIPT',
                        {marker}, {marker}, {marker}, {marker})
                """,
                (
                    entry_id,
                    cash_account_id,
                    receipt_id,
                    normalized_date,
                    normalized_amount,
                    f"{category} - {description}",
                    timestamp,
                ),
            )
            cursor = connection.execute(
                f"""
                UPDATE cash_account_balances
                SET current_balance=current_balance+{marker},
                    version=version+1, updated_at={marker}
                WHERE cash_account_id={marker} AND version={marker}
                """,
                (normalized_amount, timestamp, cash_account_id, balance["version"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("Cash balance changed while posting; please retry.")
            connection.execute(
                f"""
                INSERT INTO audit_events
                    (id, actor_user_id, action, entity_type, entity_id,
                     before_json, after_json, correlation_id, created_at)
                VALUES ({marker}, {marker}, 'COMPANY_CASH_RECEIPT_POSTED',
                        'company_receipt', {marker}, {marker}, {marker}, {marker}, {marker})
                """,
                (
                    secrets.token_urlsafe(18),
                    admin_id,
                    receipt_id,
                    json.dumps({"balance": str(current_balance)}),
                    json.dumps({
                        "balance": str(current_balance + receipt_amount),
                        "receipt_reference": receipt_reference,
                        "project_id": project_id,
                        "ledger_id": ledger_id,
                        "category": category,
                    }),
                    receipt_id,
                    timestamp,
                ),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            existing = connection.execute(
                f"SELECT * FROM company_receipts WHERE idempotency_key={marker}",
                (idempotency_key,),
            ).fetchone()
            if existing:
                entry = connection.execute(
                    f"SELECT id FROM ledger_entries WHERE company_receipt_id={marker}",
                    (existing["id"],),
                ).fetchone()
                return {
                    "id": existing["id"],
                    "amount": str(existing["amount"]),
                    "receipt_date": existing["receipt_date"],
                    "description": existing["description"],
                    "ledger_id": existing["ledger_id"],
                    "category": existing["category_name"],
                    "project_id": existing["project_id"],
                    "receipt_reference": existing["receipt_reference"],
                    "ledger_entry_id": entry["id"] if entry else None,
                    "duplicate": True,
                }
            raise exc

    create_notification(
        admin_id,
        "COMPANY_RECEIPT_POSTED",
        "Company cash receipt posted",
        f"{normalized_amount} was added to the petty cash balance.",
        "company_receipt",
        receipt_id,
    )
    try:
        invalidate_report_cache()
    except Exception:
        pass
    return {
        "id": receipt_id,
        "amount": normalized_amount,
        "receipt_date": normalized_date,
        "description": description,
        "ledger_id": ledger_id,
        "category": category,
        "project_id": project_id,
        "receipt_reference": receipt_reference,
        "ledger_entry_id": entry_id,
        "duplicate": False,
    }


def list_company_receipts(admin_id: str) -> list[dict]:
    marker = database._placeholder()
    with database.get_connection() as connection:
        _require_admin(connection, admin_id)
        rows = connection.execute(
            """
            SELECT r.id, r.cash_account_id, r.amount, r.receipt_date,
                   r.description, r.receipt_reference, r.idempotency_key,
                   r.project_id, r.ledger_id, r.category_name,
                   r.is_reversed,
                   p.name AS project_name, ld.name AS ledger_name,
                   r.created_by, r.created_at,
                   l.id AS ledger_entry_id
            FROM company_receipts r
            LEFT JOIN ledger_entries l ON l.company_receipt_id=r.id
            LEFT JOIN projects p ON p.id=r.project_id
            LEFT JOIN ledgers ld ON ld.id=r.ledger_id
            ORDER BY r.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]
