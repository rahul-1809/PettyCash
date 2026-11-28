"""Atomic Admin posting for approved petty-cash requests."""

import json
import random
import secrets
import time
from datetime import date
from decimal import Decimal
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


def _validate_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Effective posting date must be a valid ISO date.") from exc
    return value


def post_request(request_id: str, admin_id: str, effective_date: str) -> dict:
    effective_date = _validate_date(effective_date)
    marker = database._placeholder()
    max_retries = 8

    for attempt in range(max_retries):
        with database.get_connection() as connection:
            request = connection.execute(
                f"""
                SELECT * FROM petty_cash_requests WHERE id={marker}
                """,
                (request_id,),
            ).fetchone()
            if not request:
                raise LookupError("Request not found.")
            if request["status"] == "POSTED":
                raise ValueError("Request has already been posted.")
            if request["status"] not in {"APPROVED", "SUPPORTING_UPLOADED"}:
                raise ValueError("Only approved requests can be posted.")
            req_dict = dict(request)
            if req_dict.get("assigned_finance_id") and req_dict["assigned_finance_id"] != admin_id:
                raise PermissionError("This request is assigned to another Finance user.")

            account_id = request["cash_account_id"] or "system-main-cash"
            validate_date_not_in_closed_period(connection, effective_date)
            balance = connection.execute(
                f"""
                SELECT current_balance, version FROM cash_account_balances
                WHERE cash_account_id={marker}
                """,
                (account_id,),
            ).fetchone()
            if not balance:
                raise ValueError("Petty cash balance is not configured.")

            account_info = connection.execute(
                f"SELECT minimum_balance FROM cash_accounts WHERE id={marker}",
                (account_id,),
            ).fetchone()
            minimum_balance = Decimal(str(account_info["minimum_balance"])) if account_info else Decimal("0.00")

            amount = Decimal(str(request["amount"]))
            current_balance = Decimal(str(balance["current_balance"]))
            if current_balance < amount:
                raise ValueError("Insufficient petty cash balance.")
            if current_balance - amount < minimum_balance:
                raise ValueError(
                    f"Insufficient petty cash balance: transaction would breach minimum balance of ₹{minimum_balance}."
                )

            timestamp = database.now_iso()
            entry_id = secrets.token_urlsafe(18)
            try:
                cursor = connection.execute(
                    f"""
                    UPDATE cash_account_balances
                    SET current_balance=current_balance-{marker},
                        version=version+1, updated_at={marker}
                    WHERE cash_account_id={marker} AND version={marker} AND current_balance >= {marker}
                    """,
                    (str(amount), timestamp, account_id, balance["version"], str(amount)),
                )
                if cursor.rowcount != 1:
                    # Contention conflict (F-06): retry with backoff and jitter
                    if attempt < max_retries - 1:
                        connection.rollback()
                        time.sleep(0.015 * (1.5 ** attempt) + random.uniform(0.005, 0.02))
                        continue
                    raise ValueError("Balance changed during posting; please retry.")
                connection.execute(
                    f"""
                    INSERT INTO ledger_entries
                        (id, cash_account_id, request_id, entry_type, effective_date,
                         amount, description, created_at)
                    VALUES ({marker}, {marker}, {marker}, 'PAYMENT', {marker},
                            {marker}, {marker}, {marker})
                    """,
                    (
                        entry_id,
                        account_id,
                        request_id,
                        effective_date,
                        str(amount),
                        request["purpose"],
                        timestamp,
                    ),
                )
                connection.execute(
                    f"""
                    UPDATE petty_cash_requests
                    SET status='POSTED', cash_account_id={marker},
                        posted_at={marker}, updated_at={marker}
                    WHERE id={marker} AND status IN ('APPROVED', 'SUPPORTING_UPLOADED')
                    """,
                    (account_id, timestamp, timestamp, request_id),
                )
                connection.execute(
                    f"""
                    INSERT INTO request_status_history
                        (id, request_id, from_status, to_status, changed_by, reason, created_at)
                    VALUES ({marker}, {marker}, {marker}, 'POSTED',
                            {marker}, NULL, {marker})
                    """,
                    (secrets.token_urlsafe(18), request_id, request["status"], admin_id, timestamp),
                )
                connection.execute(
                    f"""
                    INSERT INTO audit_events
                        (id, actor_user_id, action, entity_type, entity_id,
                         before_json, after_json, correlation_id, created_at)
                    VALUES ({marker}, {marker}, 'PETTY_CASH_REQUEST_POSTED',
                            'petty_cash_request', {marker}, {marker}, {marker}, {marker}, {marker})
                    """,
                    (
                        secrets.token_urlsafe(18),
                        admin_id,
                        request_id,
                        json.dumps({"status": request["status"], "balance": str(current_balance)}),
                        json.dumps({"status": "POSTED", "balance": str(current_balance - amount)}),
                        entry_id,
                        timestamp,
                    ),
                )
                connection.commit()
                break
            except ValueError:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise

    with database.get_connection() as connection:
        admin_info = connection.execute(
            f"SELECT username FROM users WHERE id={database._placeholder()}",
            (admin_id,),
        ).fetchone()
    admin_name = admin_info["username"] if admin_info else "Finance"
    amt_str = f"₹{Decimal(str(request['amount'])).quantize(Decimal('0.01'))}"
    purpose_str = request["purpose"] or "Petty cash expense"

    if request["requester_id"] != admin_id:
        create_notification(
            request["requester_id"],
            "REQUEST_POSTED",
            f"Petty cash request posted by {admin_name}",
            f"Your request for {amt_str} ({purpose_str}) was posted to the canonical ledger by {admin_name} on {effective_date}.",
            "petty_cash_request",
            request_id,
        )
    if (
        request["approving_manager_id"]
        and request["approving_manager_id"] not in (request["requester_id"], admin_id)
    ):
        create_notification(
            request["approving_manager_id"],
            "REQUEST_POSTED",
            f"Petty cash request posted by {admin_name}",
            f"Request for {amt_str} ({purpose_str}) approved by you was posted to the ledger by {admin_name}.",
            "petty_cash_request",
            request_id,
        )
    try:
        invalidate_report_cache()
    except Exception:
        pass
    return {
        "request_id": request_id,
        "status": "POSTED",
        "ledger_entry_id": entry_id,
        "effective_date": effective_date,
        "amount": str(amount),
    }


def return_for_correction(request_id: str, admin_id: str, reason: str) -> dict:
    if not reason.strip():
        raise ValueError("A reason is required when returning a request for correction.")
    marker = database._placeholder()
    with database.get_connection() as connection:
        request = connection.execute(
            f"SELECT * FROM petty_cash_requests WHERE id={marker}",
            (request_id,),
        ).fetchone()
        if not request:
            raise LookupError("Request not found.")
        if request["status"] not in {"APPROVED", "SUPPORTING_UPLOADED"}:
            raise ValueError("Only approved requests can be returned for correction.")
        timestamp = database.now_iso()
        connection.execute(
            f"""
            UPDATE petty_cash_requests
            SET status='DRAFT', change_reason={marker}, updated_at={marker}
            WHERE id={marker}
            """,
            (reason.strip(), timestamp, request_id),
        )
        connection.execute(
            f"""
            INSERT INTO request_status_history
                (id, request_id, from_status, to_status, changed_by, reason, created_at)
            VALUES ({marker}, {marker}, {marker}, 'DRAFT', {marker}, {marker}, {marker})
            """,
            (secrets.token_urlsafe(18), request_id, request["status"], admin_id, reason.strip(), timestamp),
        )
        connection.execute(
            f"""
            INSERT INTO audit_events
                (id, actor_user_id, action, entity_type, entity_id,
                 before_json, after_json, correlation_id, created_at)
            VALUES ({marker}, {marker}, 'PETTY_CASH_REQUEST_RETURNED',
                    'petty_cash_request', {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                secrets.token_urlsafe(18),
                admin_id,
                request_id,
                json.dumps({"status": request["status"]}),
                json.dumps({"status": "DRAFT", "reason": reason.strip()}),
                request_id,
                timestamp,
            ),
        )
        connection.commit()
    create_notification(
        request["requester_id"],
        "REQUEST_RETURNED",
        "Petty cash request returned",
        reason.strip(),
        "petty_cash_request",
        request_id,
    )
    return {"request_id": request_id, "status": "DRAFT", "reason": reason.strip()}


def create_finance_direct_expense(
    finance_user_id: str,
    project_id: str,
    ledger_id: str,
    category: str,
    effective_date: str,
    amount,
    purpose: str,
    notes: Optional[str] = None,
    cash_account_id: str = "system-main-cash",
) -> dict:
    """Directly records and posts a Finance user's company expenditure without prior approval."""
    effective_date = _validate_date(effective_date)
    if not purpose or not purpose.strip():
        raise ValueError("Purpose is required.")
    if len(purpose) > 500:
        raise ValueError("Purpose cannot exceed 500 characters.")
    if notes and len(notes) > 2000:
        raise ValueError("Notes cannot exceed 2000 characters.")
    if not category or not category.strip():
        raise ValueError("Category is required.")

    try:
        dec_amount = Decimal(str(amount))
    except Exception:
        raise ValueError("Amount must be a valid number.")
    if dec_amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if dec_amount >= Decimal("100000000.00"):
        raise ValueError("Amount exceeds maximum allowed limit (100,000,000).")
    if round(dec_amount, 2) != dec_amount:
        raise ValueError("Amount cannot have more than 2 decimal places.")
    dec_amount = dec_amount.quantize(Decimal("0.01"))

    marker = database._placeholder()
    request_id = secrets.token_urlsafe(18)
    entry_id = secrets.token_urlsafe(18)
    max_retries = 8

    for attempt in range(max_retries):
        with database.get_connection() as connection:
            proj = connection.execute(
                f"SELECT id FROM projects WHERE id={marker} AND is_active=1",
                (project_id,),
            ).fetchone()
            ledg = connection.execute(
                f"SELECT id FROM ledgers WHERE id={marker} AND is_active=1",
                (ledger_id,),
            ).fetchone()
            if not proj or not ledg:
                raise ValueError("Active Project and Ledger are required.")

            validate_date_not_in_closed_period(connection, effective_date)

            balance = connection.execute(
                f"SELECT current_balance, version FROM cash_account_balances WHERE cash_account_id={marker}",
                (cash_account_id,),
            ).fetchone()
            if not balance:
                raise ValueError("Petty cash balance is not configured.")

            account_info = connection.execute(
                f"SELECT minimum_balance FROM cash_accounts WHERE id={marker}",
                (cash_account_id,),
            ).fetchone()
            minimum_balance = Decimal(str(account_info["minimum_balance"])) if account_info else Decimal("0.00")

            current_balance = Decimal(str(balance["current_balance"]))
            new_balance = current_balance - dec_amount
            if new_balance < minimum_balance:
                raise ValueError("Insufficient petty cash balance for this direct expense.")

            timestamp = database.now_iso()
            try:
                cursor = connection.execute(
                    f"""
                    UPDATE cash_account_balances
                    SET current_balance={marker}, version=version + 1, updated_at={marker}
                    WHERE cash_account_id={marker} AND version={marker}
                    """,
                    (str(new_balance), timestamp, cash_account_id, balance["version"]),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    if attempt < max_retries - 1:
                        time.sleep(min(0.05 * (2 ** attempt) + random.uniform(0.005, 0.025), 0.5))
                        continue
                    raise ValueError("Balance changed during posting; please retry.")

                other_user = connection.execute(
                    f"SELECT id FROM users WHERE id != {marker} ORDER BY created_at ASC LIMIT 1",
                    (finance_user_id,),
                ).fetchone()
                approver_fk_id = other_user["id"] if other_user else finance_user_id

                connection.execute(
                    f"""
                    INSERT INTO petty_cash_requests
                        (id, requester_id, approving_manager_id, assigned_finance_id, request_type,
                         project_id, ledger_id, category_id, category_name, cash_account_id,
                         request_date, amount, purpose, notes, status,
                         submitted_at, approved_at, posted_at, created_at, updated_at)
                    VALUES ({marker}, {marker}, {marker}, {marker}, 'FINANCE_DIRECT',
                            {marker}, {marker}, 'system-request-category', {marker}, {marker},
                            {marker}, {marker}, {marker}, {marker}, 'POSTED',
                            {marker}, {marker}, {marker}, {marker}, {marker})
                    """,
                    (
                        request_id,
                        finance_user_id,
                        approver_fk_id,
                        finance_user_id,
                        project_id,
                        ledger_id,
                        category.strip(),
                        cash_account_id,
                        effective_date,
                        format(dec_amount, "f"),
                        purpose.strip(),
                        notes.strip() if notes else None,
                        timestamp,
                        timestamp,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    f"""
                    INSERT INTO ledger_entries
                        (id, cash_account_id, request_id, entry_type, effective_date,
                         amount, description, created_at)
                    VALUES ({marker}, {marker}, {marker}, 'PAYMENT', {marker},
                            {marker}, {marker}, {marker})
                    """,
                    (
                        entry_id,
                        cash_account_id,
                        request_id,
                        effective_date,
                        format(dec_amount, "f"),
                        purpose.strip(),
                        timestamp,
                    ),
                )
                connection.execute(
                    f"""
                    INSERT INTO request_status_history
                        (id, request_id, from_status, to_status, changed_by, reason, created_at)
                    VALUES ({marker}, {marker}, NULL, 'POSTED', {marker}, 'Finance direct expense', {marker})
                    """,
                    (secrets.token_urlsafe(18), request_id, finance_user_id, timestamp),
                )
                connection.execute(
                    f"""
                    INSERT INTO audit_events
                        (id, actor_user_id, action, entity_type, entity_id,
                         before_json, after_json, correlation_id, created_at)
                    VALUES ({marker}, {marker}, 'FINANCE_DIRECT_EXPENSE_POSTED',
                            'petty_cash_request', {marker}, {marker}, {marker}, {marker}, {marker})
                    """,
                    (
                        secrets.token_urlsafe(18),
                        finance_user_id,
                        request_id,
                        json.dumps({"balance": str(current_balance)}),
                        json.dumps({"status": "POSTED", "amount": str(dec_amount), "balance": str(new_balance)}),
                        entry_id,
                        timestamp,
                    ),
                )
                connection.commit()
                break
            except ValueError:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise

    try:
        invalidate_report_cache()
    except Exception:
        pass
    return {
        "request_id": request_id,
        "status": "POSTED",
        "ledger_entry_id": entry_id,
        "effective_date": effective_date,
        "amount": str(dec_amount),
    }
