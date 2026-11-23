"""Financial controls, period locks, reversals, and adjustments."""

import json
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

try:
    from backend import database
    from backend.audit_service import record_audit_event
    from backend.notification_service import create_notification
except ImportError:
    import database
    from audit_service import record_audit_event
    from notification_service import create_notification


def _invalidate_cache():
    try:
        try:
            from backend.report_service import invalidate_report_cache
        except ImportError:
            from report_service import invalidate_report_cache
        invalidate_report_cache()
    except Exception:
        pass


def _validate_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Date must be a valid ISO date (YYYY-MM-DD).") from exc
    return value


def _validate_amount(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Amount must be a valid number.") from exc
    return amount


def is_date_in_closed_period(connection, date_str: str) -> bool:
    """Check whether a given date falls inside any closed financial period."""
    _validate_date(date_str)
    marker = database._placeholder()
    row = connection.execute(
        f"""
        SELECT id, period_start, period_end
        FROM financial_periods
        WHERE status = 'CLOSED'
          AND {marker} >= period_start
          AND {marker} <= period_end
        """,
        (date_str, date_str),
    ).fetchone()
    return bool(row)


def validate_date_not_in_closed_period(connection, date_str: str) -> None:
    """Raise ValueError if the date falls inside a closed financial period."""
    if is_date_in_closed_period(connection, date_str):
        raise ValueError(
            f"Financial period for date {date_str} is closed. Modifications are locked."
        )


# ─── Financial Period Management ─────────────────────────────────────────────

def create_financial_period(admin_id: str, period_start: str, period_end: str) -> dict:
    """Create a new financial period in OPEN status."""
    start = _validate_date(period_start)
    end = _validate_date(period_end)
    if start > end:
        raise ValueError("period_start cannot be after period_end.")

    period_id = secrets.token_urlsafe(18)
    timestamp = database.now_iso()
    marker = database._placeholder()

    with database.get_connection() as connection:
        # Check for existing period
        existing = connection.execute(
            f"SELECT id FROM financial_periods WHERE period_start = {marker} AND period_end = {marker}",
            (start, end),
        ).fetchone()
        if existing:
            raise ValueError(f"Financial period {start} to {end} already exists.")

        connection.execute(
            f"""
            INSERT INTO financial_periods
                (id, period_start, period_end, status, created_at)
            VALUES ({marker}, {marker}, {marker}, 'OPEN', {marker})
            """,
            (period_id, start, end, timestamp),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="FINANCIAL_PERIOD_CREATED",
            entity_type="financial_period",
            entity_id=period_id,
            after={"period_start": start, "period_end": end, "status": "OPEN"},
        )
        connection.commit()

    return {
        "id": period_id,
        "period_start": start,
        "period_end": end,
        "status": "OPEN",
        "created_at": timestamp,
    }


def close_financial_period(period_id: str, admin_id: str) -> dict:
    """Close a financial period, locking all financial transactions within its range."""
    marker = database._placeholder()
    timestamp = database.now_iso()
    with database.get_connection() as connection:
        row = connection.execute(
            f"SELECT * FROM financial_periods WHERE id = {marker}",
            (period_id,),
        ).fetchone()
        if not row:
            raise LookupError("Financial period not found.")
        if row["status"] == "CLOSED":
            raise ValueError("Financial period is already closed.")

        connection.execute(
            f"""
            UPDATE financial_periods
            SET status = 'CLOSED', closed_by = {marker}, closed_at = {marker}
            WHERE id = {marker}
            """,
            (admin_id, timestamp, period_id),
        )
        user_row = connection.execute(
            f"SELECT username FROM users WHERE id = {marker}",
            (admin_id,),
        ).fetchone()
        admin_username = user_row["username"] if user_row and "username" in user_row.keys() else admin_id

        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="FINANCIAL_PERIOD_CLOSED",
            entity_type="financial_period",
            entity_id=period_id,
            before={"status": "OPEN"},
            after={"status": "CLOSED", "closed_by": admin_id, "closed_at": timestamp},
        )
        connection.commit()

    _invalidate_cache()
    return {
        "id": period_id,
        "status": "CLOSED",
        "closed_by": admin_id,
        "closed_by_username": admin_username,
        "closed_by_name": admin_username,
        "closed_at": timestamp,
    }


def reopen_financial_period(period_id: str, admin_id: str) -> dict:
    """Reopen a previously closed financial period (Admin only)."""
    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"SELECT * FROM financial_periods WHERE id = {marker}",
            (period_id,),
        ).fetchone()
        if not row:
            raise LookupError("Financial period not found.")
        if row["status"] == "OPEN":
            raise ValueError("Financial period is already open.")

        connection.execute(
            f"""
            UPDATE financial_periods
            SET status = 'OPEN', closed_by = NULL, closed_at = NULL
            WHERE id = {marker}
            """,
            (period_id,),
        )
        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="FINANCIAL_PERIOD_REOPENED",
            entity_type="financial_period",
            entity_id=period_id,
            before={"status": "CLOSED", "closed_by": row["closed_by"]},
            after={"status": "OPEN"},
        )
        connection.commit()

    _invalidate_cache()
    return {"id": period_id, "status": "OPEN"}


def list_financial_periods() -> List[Dict[str, Any]]:
    """List all financial periods ordered by period_start descending."""
    with database.get_connection() as connection:
        rows = connection.execute(
            """
            SELECT p.id, p.period_start, p.period_end, p.status,
                   p.closed_by,
                   COALESCE(u.username, p.closed_by) AS closed_by_username,
                   u.username AS closed_by_name,
                   p.closed_at, p.created_at
            FROM financial_periods p
            LEFT JOIN users u ON u.id = p.closed_by
            ORDER BY p.period_start DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Reversals & Adjustments ─────────────────────────────────────────────────

def reverse_posted_request(
    request_id: str,
    admin_id: str,
    reason: str,
    effective_date: Optional[str] = None,
) -> dict:
    """Reverse a posted petty cash request atomically.
    
    Restores the disbursed amount to the cash account balance,
    marks the request and ledger entry as reversed,
    records a reversal adjustment entry, and logs an immutable audit event.
    """
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValueError("A reason is required to reverse a posted request.")

    timestamp = database.now_iso()
    reversal_date = _validate_date(effective_date or date.today().isoformat())
    marker = database._placeholder()

    with database.get_connection() as connection:
        validate_date_not_in_closed_period(connection, reversal_date)

        request = connection.execute(
            f"SELECT * FROM petty_cash_requests WHERE id = {marker}",
            (request_id,),
        ).fetchone()
        if not request:
            raise LookupError("Request not found.")
        if request["status"] != "POSTED":
            raise ValueError("Only POSTED requests can be reversed.")
        if request["is_reversed"]:
            raise ValueError("This request has already been reversed.")

        # Find corresponding ledger entry
        ledger_entry = connection.execute(
            f"SELECT * FROM ledger_entries WHERE request_id = {marker}",
            (request_id,),
        ).fetchone()

        account_id = request["cash_account_id"] or "system-main-cash"
        balance_row = connection.execute(
            f"SELECT current_balance, version FROM cash_account_balances WHERE cash_account_id = {marker}",
            (account_id,),
        ).fetchone()
        if not balance_row:
            raise ValueError("Cash account balance not configured.")

        amount = Decimal(str(request["amount"]))
        current_balance = Decimal(str(balance_row["current_balance"]))
        new_balance = current_balance + amount
        adjustment_id = secrets.token_urlsafe(18)

        # 1. Update balance optimistically
        cur = connection.execute(
            f"""
            UPDATE cash_account_balances
            SET current_balance = current_balance + {marker},
                version = version + 1,
                updated_at = {marker}
            WHERE cash_account_id = {marker} AND version = {marker}
            """,
            (str(amount), timestamp, account_id, balance_row["version"]),
        )
        if cur.rowcount != 1:
            raise ValueError("Balance changed concurrently; please retry reversal.")

        # 2. Mark request as reversed
        connection.execute(
            f"""
            UPDATE petty_cash_requests
            SET is_reversed = 1, reversed_at = {marker}, reversed_by = {marker},
                reversal_reason = {marker}, updated_at = {marker}
            WHERE id = {marker}
            """,
            (timestamp, admin_id, clean_reason, timestamp, request_id),
        )

        # 3. Mark ledger entry as reversed if present
        if ledger_entry:
            connection.execute(
                f"""
                UPDATE ledger_entries
                SET is_reversed = 1, reversed_at = {marker}
                WHERE id = {marker}
                """,
                (timestamp, ledger_entry["id"]),
            )

        # 4. Record status history
        connection.execute(
            f"""
            INSERT INTO request_status_history
                (id, request_id, from_status, to_status, changed_by, reason, created_at)
            VALUES ({marker}, {marker}, 'POSTED', 'REVERSED', {marker}, {marker}, {marker})
            """,
            (secrets.token_urlsafe(18), request_id, admin_id, clean_reason, timestamp),
        )

        # 5. Insert ledger adjustment record
        connection.execute(
            f"""
            INSERT INTO ledger_adjustments
                (id, cash_account_id, adjustment_type, related_ledger_entry_id,
                 related_request_id, direction, amount, effective_date, reason,
                 created_by, created_at)
            VALUES ({marker}, {marker}, 'REVERSAL', {marker}, {marker},
                    'INFLOW', {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                adjustment_id,
                account_id,
                ledger_entry["id"] if ledger_entry else None,
                request_id,
                str(amount),
                reversal_date,
                clean_reason,
                admin_id,
                timestamp,
            ),
        )

        # 6. Immutable audit event
        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="PETTY_CASH_REQUEST_REVERSED",
            entity_type="petty_cash_request",
            entity_id=request_id,
            before={"is_reversed": 0, "balance": str(current_balance)},
            after={
                "is_reversed": 1,
                "reversal_reason": clean_reason,
                "balance": str(new_balance),
                "adjustment_id": adjustment_id,
            },
            correlation_id=adjustment_id,
        )
        connection.commit()

    create_notification(
        request["requester_id"],
        "REQUEST_REVERSED",
        "Petty cash request reversed",
        f"Your posted request of ₹{amount} has been reversed: {clean_reason}",
        "petty_cash_request",
        request_id,
    )

    _invalidate_cache()
    return {
        "request_id": request_id,
        "is_reversed": True,
        "amount": str(amount),
        "new_balance": str(new_balance),
        "adjustment_id": adjustment_id,
        "reason": clean_reason,
    }


def reverse_company_receipt(
    receipt_id: str,
    admin_id: str,
    reason: str,
    effective_date: Optional[str] = None,
) -> dict:
    """Reverse a company cash receipt atomically.
    
    Deducts the receipt amount from the balance (verifying minimum balance),
    marks the receipt and ledger entry as reversed,
    records a reversal adjustment entry, and logs an immutable audit event.
    """
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValueError("A reason is required to reverse a company receipt.")

    timestamp = database.now_iso()
    reversal_date = _validate_date(effective_date or date.today().isoformat())
    marker = database._placeholder()

    with database.get_connection() as connection:
        validate_date_not_in_closed_period(connection, reversal_date)

        receipt = connection.execute(
            f"SELECT * FROM company_receipts WHERE id = {marker}",
            (receipt_id,),
        ).fetchone()
        if not receipt:
            raise LookupError("Company receipt not found.")
        if receipt["is_reversed"]:
            raise ValueError("This company receipt has already been reversed.")

        account_id = receipt["cash_account_id"] or "system-main-cash"
        balance_row = connection.execute(
            f"""
            SELECT b.current_balance, b.version, a.minimum_balance
            FROM cash_account_balances b
            JOIN cash_accounts a ON a.id = b.cash_account_id
            WHERE b.cash_account_id = {marker}
            """,
            (account_id,),
        ).fetchone()
        if not balance_row:
            raise ValueError("Cash account balance not configured.")

        amount = Decimal(str(receipt["amount"]))
        current_balance = Decimal(str(balance_row["current_balance"]))
        minimum_balance = Decimal(str(balance_row["minimum_balance"]))

        # Enforce negative-balance rules
        if current_balance - amount < minimum_balance:
            raise ValueError(
                f"Cannot reverse receipt: remaining balance would fall below minimum allowed (₹{minimum_balance})."
            )

        new_balance = current_balance - amount
        adjustment_id = secrets.token_urlsafe(18)

        # 1. Update balance optimistically
        cur = connection.execute(
            f"""
            UPDATE cash_account_balances
            SET current_balance = current_balance - {marker},
                version = version + 1,
                updated_at = {marker}
            WHERE cash_account_id = {marker} AND version = {marker}
            """,
            (str(amount), timestamp, account_id, balance_row["version"]),
        )
        if cur.rowcount != 1:
            raise ValueError("Balance changed concurrently; please retry reversal.")

        # 2. Mark receipt as reversed
        connection.execute(
            f"""
            UPDATE company_receipts
            SET is_reversed = 1, reversed_at = {marker}, reversed_by = {marker},
                reversal_reason = {marker}
            WHERE id = {marker}
            """,
            (timestamp, admin_id, clean_reason, receipt_id),
        )

        # 3. Mark ledger entry as reversed
        ledger_entry = connection.execute(
            f"SELECT id FROM ledger_entries WHERE company_receipt_id = {marker}",
            (receipt_id,),
        ).fetchone()
        if ledger_entry:
            connection.execute(
                f"""
                UPDATE ledger_entries
                SET is_reversed = 1, reversed_at = {marker}
                WHERE id = {marker}
                """,
                (timestamp, ledger_entry["id"]),
            )

        # 4. Insert ledger adjustment record
        connection.execute(
            f"""
            INSERT INTO ledger_adjustments
                (id, cash_account_id, adjustment_type, related_ledger_entry_id,
                 related_company_receipt_id, direction, amount, effective_date,
                 reason, created_by, created_at)
            VALUES ({marker}, {marker}, 'REVERSAL', {marker}, {marker},
                    'OUTFLOW', {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                adjustment_id,
                account_id,
                ledger_entry["id"] if ledger_entry else None,
                receipt_id,
                str(amount),
                reversal_date,
                clean_reason,
                admin_id,
                timestamp,
            ),
        )

        # 5. Immutable audit event
        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="COMPANY_RECEIPT_REVERSED",
            entity_type="company_receipt",
            entity_id=receipt_id,
            before={"is_reversed": 0, "balance": str(current_balance)},
            after={
                "is_reversed": 1,
                "reversal_reason": clean_reason,
                "balance": str(new_balance),
                "adjustment_id": adjustment_id,
            },
            correlation_id=adjustment_id,
        )
        connection.commit()

    _invalidate_cache()
    return {
        "receipt_id": receipt_id,
        "is_reversed": True,
        "amount": str(amount),
        "new_balance": str(new_balance),
        "adjustment_id": adjustment_id,
        "reason": clean_reason,
    }


def create_balance_adjustment(
    admin_id: str,
    amount: Any,
    effective_date: str,
    reason: str,
    direction: str,
    cash_account_id: str = "system-main-cash",
) -> dict:
    """Post an authorized balance adjustment entry (INFLOW or OUTFLOW).
    
    Verifies that the date is not in a closed financial period,
    verifies minimum balance rules for outflows,
    updates cash balance atomically with row version check,
    records a ledger adjustment record, and writes an audit event.
    """
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValueError("A reason is required for balance adjustment.")
    if direction not in {"INFLOW", "OUTFLOW"}:
        raise ValueError("Adjustment direction must be INFLOW or OUTFLOW.")

    normalized_amount = _validate_amount(amount)
    if normalized_amount <= 0:
        raise ValueError("Adjustment amount must be positive.")

    adj_date = _validate_date(effective_date)
    timestamp = database.now_iso()
    adjustment_id = secrets.token_urlsafe(18)
    marker = database._placeholder()

    with database.get_connection() as connection:
        validate_date_not_in_closed_period(connection, adj_date)

        balance_row = connection.execute(
            f"""
            SELECT b.current_balance, b.version, a.minimum_balance
            FROM cash_account_balances b
            JOIN cash_accounts a ON a.id = b.cash_account_id
            WHERE b.cash_account_id = {marker}
            """,
            (cash_account_id,),
        ).fetchone()
        if not balance_row:
            raise ValueError(f"Cash account '{cash_account_id}' balance not configured.")

        current_balance = Decimal(str(balance_row["current_balance"]))
        minimum_balance = Decimal(str(balance_row["minimum_balance"]))

        if direction == "OUTFLOW":
            if current_balance - normalized_amount < minimum_balance:
                raise ValueError(
                    f"Insufficient funds: adjustment would breach minimum balance of ₹{minimum_balance}."
                )
            new_balance = current_balance - normalized_amount
            balance_delta_sql = f"current_balance - {marker}"
        else:
            new_balance = current_balance + normalized_amount
            balance_delta_sql = f"current_balance + {marker}"

        cur = connection.execute(
            f"""
            UPDATE cash_account_balances
            SET current_balance = {balance_delta_sql},
                version = version + 1,
                updated_at = {marker}
            WHERE cash_account_id = {marker} AND version = {marker}
            """,
            (str(normalized_amount), timestamp, cash_account_id, balance_row["version"]),
        )
        if cur.rowcount != 1:
            raise ValueError("Balance changed concurrently; please retry adjustment.")

        connection.execute(
            f"""
            INSERT INTO ledger_adjustments
                (id, cash_account_id, adjustment_type, direction,
                 amount, effective_date, reason, created_by, created_at)
            VALUES ({marker}, {marker}, 'ADJUSTMENT', {marker},
                    {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                adjustment_id,
                cash_account_id,
                direction,
                str(normalized_amount),
                adj_date,
                clean_reason,
                admin_id,
                timestamp,
            ),
        )

        record_audit_event(
            connection=connection,
            actor_user_id=admin_id,
            action="BALANCE_ADJUSTMENT_POSTED",
            entity_type="ledger_adjustment",
            entity_id=adjustment_id,
            before={"balance": str(current_balance)},
            after={
                "balance": str(new_balance),
                "direction": direction,
                "amount": str(normalized_amount),
                "effective_date": adj_date,
                "reason": clean_reason,
            },
            correlation_id=adjustment_id,
        )
        connection.commit()

    _invalidate_cache()
    return {
        "id": adjustment_id,
        "cash_account_id": cash_account_id,
        "direction": direction,
        "amount": str(normalized_amount),
        "effective_date": adj_date,
        "new_balance": str(new_balance),
        "reason": clean_reason,
    }


def list_adjustments(cash_account_id: str = "system-main-cash") -> List[Dict[str, Any]]:
    """List adjustments and reversals for a cash account, newest first."""
    marker = database._placeholder()
    query = f"""
        SELECT a.id, a.cash_account_id, a.adjustment_type, a.direction,
               a.amount, a.effective_date, a.reason,
               a.related_request_id, a.related_company_receipt_id,
               a.created_by, u.username AS created_by_username, a.created_at
        FROM ledger_adjustments a
        LEFT JOIN users u ON u.id = a.created_by
        WHERE a.cash_account_id = {marker}
        ORDER BY a.created_at DESC
    """
    with database.get_connection() as connection:
        rows = connection.execute(query, (cash_account_id,)).fetchall()
        return [dict(r) for r in rows]
