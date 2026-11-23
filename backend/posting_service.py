"""Atomic Admin posting for approved petty-cash requests."""

import json
import secrets
from datetime import date
from decimal import Decimal

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
        if request["status"] != "SUPPORTING_UPLOADED":
            raise ValueError("Only approved requests with supporting files can be posted.")
        files = connection.execute(
            f"SELECT id FROM supporting_files WHERE request_id={marker}",
            (request_id,),
        ).fetchall()
        if not files:
            raise ValueError("At least one supporting file is required before posting.")

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
                WHERE id={marker} AND status='SUPPORTING_UPLOADED'
                """,
                (account_id, timestamp, timestamp, request_id),
            )
            connection.execute(
                f"""
                INSERT INTO request_status_history
                    (id, request_id, from_status, to_status, changed_by, reason, created_at)
                VALUES ({marker}, {marker}, 'SUPPORTING_UPLOADED', 'POSTED',
                        {marker}, NULL, {marker})
                """,
                (secrets.token_urlsafe(18), request_id, admin_id, timestamp),
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
        except Exception:
            connection.rollback()
            raise

    with database.get_connection() as connection:
        admin_info = connection.execute(
            f"SELECT username FROM users WHERE id={database._placeholder()}",
            (admin_id,),
        ).fetchone()
    admin_name = admin_info["username"] if admin_info else "Admin"
    amt_str = f"₹{Decimal(str(request['amount'])).quantize(Decimal('0.01'))}"
    purpose_str = request["purpose"] or "Petty cash expense"

    create_notification(
        request["requester_id"],
        "REQUEST_POSTED",
        f"Petty cash request posted by Admin {admin_name}",
        f"Your request for {amt_str} ({purpose_str}) was posted to the canonical ledger by Admin {admin_name} on {effective_date}.",
        "petty_cash_request",
        request_id,
    )
    if request["approving_manager_id"] and request["approving_manager_id"] != request["requester_id"]:
        create_notification(
            request["approving_manager_id"],
            "REQUEST_POSTED",
            f"Petty cash request posted by Admin {admin_name}",
            f"Request for {amt_str} ({purpose_str}) approved by you was posted to the ledger by Admin {admin_name}.",
            "petty_cash_request",
            request_id,
        )
    if admin_id and admin_id not in (request["requester_id"], request["approving_manager_id"]):
        create_notification(
            admin_id,
            "REQUEST_POSTED",
            "Petty cash request posted successfully",
            f"Request for {amt_str} ({purpose_str}) was successfully posted to the ledger on {effective_date}.",
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
