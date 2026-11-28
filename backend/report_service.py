"""Monthly financial reporting, 12-column standardized Excel exports, and ZIP bundles."""

import base64
import calendar
import datetime
import io
import os
import re
import time
import zipfile
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink

try:
    from backend import database
    from backend.supporting_service import storage_root
except ImportError:
    import database
    from supporting_service import storage_root


# Standard styling matching financial reporting guidelines
THIN_SIDE = Side(border_style="thin", color="D0D5DD")
BORDER_ALL_THIN = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

FILL_HEADER = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")  # Slate 800
FILL_ZEBRA = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")   # Slate 50
FILL_HIGHLIGHT = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
YELLOW_FILL = PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")
HEADER_BLUE_FILL = PatternFill(start_color="FF4F81BD", end_color="FF4F81BD", fill_type="solid")

FONT_HEADER = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
FONT_TITLE = Font(name="Calibri", size=13, bold=True, color="0F172A")
FONT_TITLE_WHITE = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
FONT_SUBTITLE = Font(name="Calibri", size=10, italic=True, color="475569")
FONT_REGULAR = Font(name="Calibri", size=10, bold=False, color="1E293B")
FONT_BOLD = Font(name="Calibri", size=10, bold=True, color="1E293B")
FONT_LINK = Font(name="Calibri", size=10, bold=False, color="2563EB", underline="single")

REQUIRED_12_COLUMNS = [
    "Date",
    "Ledger",
    "Description",
    "Receipt",
    "Payment",
    "Outstanding Balance",
    "Approved By",
    "Requested By",
    "Category",
    "Project",
    "Supportings",
    "Notes",
]


def _scalar(row: Any, default: Any = 0) -> Any:
    """Safely extract scalar from a single-column query result (works with SQLite tuple/Row and psycopg dict_row)."""
    if not row:
        return default
    if isinstance(row, dict):
        return next(iter(row.values()), default)
    try:
        return row[0]
    except (KeyError, IndexError, TypeError):
        return default


def parse_month_bounds(month_str: str) -> Tuple[str, str, int, int]:
    """Parse 'YYYY-MM' into (start_date, end_date, year, month)."""
    match = re.match(r"^(\d{4})-(\d{2})$", (month_str or "").strip())
    if not match:
        raise ValueError("Month must be in YYYY-MM format (e.g. '2026-11').")
    year = int(match.group(1))
    month = int(match.group(2))
    if not (1 <= month <= 12):
        raise ValueError("Month must be between 01 and 12.")
    _, last_day = calendar.monthrange(year, month)
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
    return start_date, end_date, year, month


_REPORT_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_REPORT_CACHE_TTL: float = 60.0  # Cache reports for 60 seconds


def invalidate_report_cache() -> None:
    """Purge in-memory cached report calculations."""
    global _REPORT_CACHE
    _REPORT_CACHE.clear()


def get_monthly_report_data(month_str: str, cash_account_id: str = "system-main-cash") -> Dict[str, Any]:
    """Compile comprehensive authoritative monthly report data.
    
    Excludes unposted/pending requests from posted totals and balances.
    Calculates exact opening balance, daily cash movements, and spending breakdowns.
    """
    is_testing = os.getenv("TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ
    cache_key = f"{month_str}:{cash_account_id}"
    now = time.time()
    if not is_testing and cache_key in _REPORT_CACHE:
        cached_ts, cached_data = _REPORT_CACHE[cache_key]
        if now - cached_ts < _REPORT_CACHE_TTL:
            return cached_data

    start_date, end_date, year, month = parse_month_bounds(month_str)
    month_name = calendar.month_name[month]
    marker = database._placeholder()

    with database.get_connection() as connection:
        # 1. Authoritative initial balance of cash account
        account_row = connection.execute(
            f"SELECT opening_balance, minimum_balance FROM cash_accounts WHERE id={marker}",
            (cash_account_id,),
        ).fetchone()
        initial_account_balance = Decimal(str(account_row["opening_balance"] if account_row else "0.00"))

        bal_row = connection.execute(
            f"SELECT current_balance FROM cash_account_balances WHERE cash_account_id={marker}",
            (cash_account_id,),
        ).fetchone()
        if initial_account_balance == 0 and bal_row:
            # Reconcile base initial balance from current balance minus net ledger movements
            all_receipts = Decimal(str(_scalar(connection.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE cash_account_id={marker} AND entry_type='RECEIPT' AND is_reversed=0",
                (cash_account_id,),
            ).fetchone())))
            all_payments = Decimal(str(_scalar(connection.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE cash_account_id={marker} AND entry_type='PAYMENT' AND is_reversed=0",
                (cash_account_id,),
            ).fetchone())))
            all_adj_in = Decimal(str(_scalar(connection.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM ledger_adjustments WHERE cash_account_id={marker} AND direction='INFLOW'",
                (cash_account_id,),
            ).fetchone())))
            all_adj_out = Decimal(str(_scalar(connection.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM ledger_adjustments WHERE cash_account_id={marker} AND direction='OUTFLOW'",
                (cash_account_id,),
            ).fetchone())))
            cur_bal = Decimal(str(bal_row["current_balance"]))
            initial_account_balance = cur_bal - (all_receipts + all_adj_in) + (all_payments + all_adj_out)

        # 2. Prior movements before start_date to determine opening balance for this month
        prior_receipts_row = connection.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0)
            FROM ledger_entries
            WHERE cash_account_id={marker}
              AND effective_date < {marker}
              AND entry_type = 'RECEIPT'
              AND is_reversed = 0
            """,
            (cash_account_id, start_date),
        ).fetchone()
        prior_receipts = Decimal(str(_scalar(prior_receipts_row)))

        prior_payments_row = connection.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0)
            FROM ledger_entries
            WHERE cash_account_id={marker}
              AND effective_date < {marker}
              AND entry_type = 'PAYMENT'
              AND is_reversed = 0
            """,
            (cash_account_id, start_date),
        ).fetchone()
        prior_payments = Decimal(str(_scalar(prior_payments_row)))

        # Prior adjustments
        prior_adj_in_row = connection.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0)
            FROM ledger_adjustments
            WHERE cash_account_id={marker}
              AND effective_date < {marker}
              AND direction = 'INFLOW'
            """,
            (cash_account_id, start_date),
        ).fetchone()
        prior_adj_in = Decimal(str(_scalar(prior_adj_in_row)))

        prior_adj_out_row = connection.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0)
            FROM ledger_adjustments
            WHERE cash_account_id={marker}
              AND effective_date < {marker}
              AND direction = 'OUTFLOW'
            """,
            (cash_account_id, start_date),
        ).fetchone()
        prior_adj_out = Decimal(str(_scalar(prior_adj_out_row)))

        opening_balance = initial_account_balance + prior_receipts + prior_adj_in - prior_payments - prior_adj_out

        # 3. Active posted ledger entries within the month
        entries_query = f"""
            SELECT l.id AS ledger_entry_id, l.entry_type, l.effective_date,
                   l.amount, l.description AS entry_description, l.created_at,
                   l.request_id, l.company_receipt_id,
                   r.purpose AS request_purpose, r.notes AS request_notes,
                   r.category_name AS request_category,
                   p.name AS project_name, ld.name AS ledger_name,
                   req_u.username AS requester_username,
                   mgr_u.username AS manager_username,
                   cr.receipt_reference, cr.description AS receipt_description,
                   cr.category_name AS receipt_category,
                   cr_p.name AS cr_project_name, cr_l.name AS cr_ledger_name,
                   cr_u.username AS cr_creator_username
            FROM ledger_entries l
            LEFT JOIN petty_cash_requests r ON r.id = l.request_id
            LEFT JOIN projects p ON p.id = r.project_id
            LEFT JOIN ledgers ld ON ld.id = r.ledger_id
            LEFT JOIN users req_u ON req_u.id = r.requester_id
            LEFT JOIN users mgr_u ON mgr_u.id = r.approving_manager_id
            LEFT JOIN company_receipts cr ON cr.id = l.company_receipt_id
            LEFT JOIN projects cr_p ON cr_p.id = cr.project_id
            LEFT JOIN ledgers cr_l ON cr_l.id = cr.ledger_id
            LEFT JOIN users cr_u ON cr_u.id = cr.created_by
            WHERE l.cash_account_id = {marker}
              AND l.effective_date >= {marker}
              AND l.effective_date <= {marker}
              AND l.is_reversed = 0
            ORDER BY l.effective_date ASC, l.created_at ASC
        """
        raw_entries = connection.execute(entries_query, (cash_account_id, start_date, end_date)).fetchall()

        # Fetch supporting files for requests in this month
        req_ids = [r["request_id"] for r in raw_entries if r["request_id"]]
        supporting_files_by_request: Dict[str, List[dict]] = {}
        all_supporting_files: List[dict] = []

        if req_ids:
            placeholders = ",".join([marker] * len(req_ids))
            files_rows = connection.execute(
                f"""
                SELECT s.id, s.request_id, s.storage_key, s.original_filename,
                       s.size_bytes, s.created_at, s.file_data, u.username AS uploaded_by_username
                FROM supporting_files s
                LEFT JOIN users u ON u.id = s.uploaded_by
                WHERE s.request_id IN ({placeholders})
                ORDER BY s.created_at ASC
                """,
                tuple(req_ids),
            ).fetchall()
            for f in files_rows:
                fd = dict(f)
                supporting_files_by_request.setdefault(fd["request_id"], []).append(fd)
                all_supporting_files.append(fd)

        # 4. Fetch adjustments for the month
        adj_rows = connection.execute(
            f"""
            SELECT a.id, a.adjustment_type, a.direction, a.amount,
                   a.effective_date, a.reason, a.created_at,
                   u.username AS creator_username
            FROM ledger_adjustments a
            LEFT JOIN users u ON u.id = a.created_by
            WHERE a.cash_account_id = {marker}
              AND a.effective_date >= {marker}
              AND a.effective_date <= {marker}
            ORDER BY a.effective_date ASC, a.created_at ASC
            """,
            (cash_account_id, start_date, end_date),
        ).fetchall()

        # Combine ledger entries and standalone adjustments in chronological order
        combined_items = []
        for row in raw_entries:
            combined_items.append({"source": "ledger_entry", "row": dict(row), "date": row["effective_date"], "created_at": row["created_at"]})
        for adj in adj_rows:
            combined_items.append({"source": "adjustment", "row": dict(adj), "date": adj["effective_date"], "created_at": adj["created_at"]})
        combined_items.sort(key=lambda x: (x["date"], x["created_at"]))

        # Build normalized posted entries with running balance
        running_balance = opening_balance
        total_receipts = Decimal("0.00")
        total_payments = Decimal("0.00")
        posted_entries = []

        # Tracking for breakdowns
        daily_movement_dict: Dict[str, Dict[str, Decimal]] = {}
        ledger_breakdown_dict: Dict[str, Dict[str, Any]] = {}
        category_breakdown_dict: Dict[str, Dict[str, Any]] = {}
        project_breakdown_dict: Dict[str, Dict[str, Any]] = {}
        receipt_ledger_breakdown_dict: Dict[str, Dict[str, Any]] = {}
        receipt_project_breakdown_dict: Dict[str, Dict[str, Any]] = {}

        for item in combined_items:
            tx_date = item["date"]
            if tx_date not in daily_movement_dict:
                daily_movement_dict[tx_date] = {"receipts": Decimal("0.00"), "payments": Decimal("0.00")}

            if item["source"] == "ledger_entry":
                r = item["row"]
                amt = Decimal(str(r["amount"]))
                if r["entry_type"] == "RECEIPT":
                    receipt_amt = amt
                    payment_amt = Decimal("0.00")
                    running_balance += amt
                    total_receipts += amt
                    daily_movement_dict[tx_date]["receipts"] += amt

                    ledger_name = r["cr_ledger_name"] or "Company Receipts"
                    desc = r["receipt_description"] or r["entry_description"]
                    approved_by = r["cr_creator_username"] or "Admin"
                    requested_by = "Company"
                    cat_name = r["receipt_category"] or "Cash replenishment"
                    proj_name = r["cr_project_name"] or "Petty Cash HQ"
                    supportings_list = []
                    primary_file = None
                    notes = ""

                    # Accumulate breakdowns for receipts
                    _accumulate_breakdown(receipt_ledger_breakdown_dict, ledger_name, amt)
                    _accumulate_breakdown(receipt_project_breakdown_dict, proj_name, amt)
                else:  # PAYMENT
                    receipt_amt = Decimal("0.00")
                    payment_amt = amt
                    running_balance -= amt
                    total_payments += amt
                    daily_movement_dict[tx_date]["payments"] += amt

                    ledger_name = r["ledger_name"] or "General"
                    desc = r["request_purpose"] or r["entry_description"]
                    approved_by = r["manager_username"] or ""
                    requested_by = r["requester_username"] or ""
                    cat_name = r["request_category"] or "General Expense"
                    proj_name = r["project_name"] or "General"
                    req_id = r["request_id"]
                    supportings_list = supporting_files_by_request.get(req_id, [])
                    primary_file = supportings_list[0]["original_filename"] if supportings_list else ""
                    notes = r["request_notes"] or ""

                    # Accumulate breakdowns for spending (payments only)
                    _accumulate_breakdown(ledger_breakdown_dict, ledger_name, amt)
                    _accumulate_breakdown(category_breakdown_dict, cat_name, amt)
                    _accumulate_breakdown(project_breakdown_dict, proj_name, amt)

                posted_entries.append({
                    "id": r["ledger_entry_id"],
                    "request_id": r["request_id"],
                    "date": tx_date,
                    "ledger": ledger_name,
                    "description": desc,
                    "receipt": float(receipt_amt) if receipt_amt > 0 else None,
                    "payment": float(payment_amt) if payment_amt > 0 else None,
                    "outstanding_balance": float(running_balance),
                    "approved_by": approved_by,
                    "requested_by": requested_by,
                    "category": cat_name,
                    "project": proj_name,
                    "supportings": primary_file,
                    "all_supportings": supportings_list,
                    "supporting_count": len(supportings_list),
                    "voucher_status": (
                        "Posted (Voucher Attached)"
                        if len(supportings_list) > 0
                        else ("Posted (Voucher Pending)" if payment_amt > 0 else "Receipt")
                    ),
                    "notes": notes,
                })

            else:  # adjustment
                adj = item["row"]
                amt = Decimal(str(adj["amount"]))
                if adj["direction"] == "INFLOW":
                    receipt_amt = amt
                    payment_amt = Decimal("0.00")
                    running_balance += amt
                    total_receipts += amt
                    daily_movement_dict[tx_date]["receipts"] += amt
                else:
                    receipt_amt = Decimal("0.00")
                    payment_amt = amt
                    running_balance -= amt
                    total_payments += amt
                    daily_movement_dict[tx_date]["payments"] += amt
                    _accumulate_breakdown(ledger_breakdown_dict, "Adjustment", amt)
                    _accumulate_breakdown(category_breakdown_dict, "Adjustment", amt)
                    _accumulate_breakdown(project_breakdown_dict, "Adjustment", amt)

                posted_entries.append({
                    "id": adj["id"],
                    "request_id": None,
                    "date": tx_date,
                    "ledger": "Adjustment",
                    "description": adj["reason"],
                    "receipt": float(receipt_amt) if receipt_amt > 0 else None,
                    "payment": float(payment_amt) if payment_amt > 0 else None,
                    "outstanding_balance": float(running_balance),
                    "approved_by": adj["creator_username"] or "Admin",
                    "requested_by": adj["creator_username"] or "Admin",
                    "category": "Adjustment",
                    "project": "Adjustment",
                    "supportings": "",
                    "all_supportings": [],
                    "notes": adj["reason"],
                })

        closing_balance = running_balance
        net_movement = total_receipts - total_payments

        # Daily movement summary with running balance
        daily_movement = []
        cur_bal = opening_balance
        for d in sorted(daily_movement_dict.keys()):
            rec = daily_movement_dict[d]["receipts"]
            pay = daily_movement_dict[d]["payments"]
            cur_bal = cur_bal + rec - pay
            daily_movement.append({
                "date": d,
                "receipts": float(rec),
                "payments": float(pay),
                "net_movement": float(rec - pay),
                "closing_balance": float(cur_bal),
            })

        # 5. Unposted / Pending / Rejected Requests (FILTERED BY REQUEST_DATE)
        # CRUCIAL: strictly excluded from posted totals!
        unposted_query = f"""
            SELECT r.id, r.request_date, r.amount, r.purpose, r.status,
                   r.change_reason, r.rejection_reason,
                   p.name AS project_name, l.name AS ledger_name, r.category_name,
                   req_u.username AS requester_username,
                   mgr_u.username AS manager_username
            FROM petty_cash_requests r
            LEFT JOIN projects p ON p.id = r.project_id
            LEFT JOIN ledgers l ON l.id = r.ledger_id
            LEFT JOIN users req_u ON req_u.id = r.requester_id
            LEFT JOIN users mgr_u ON mgr_u.id = r.approving_manager_id
            WHERE r.request_date >= {marker}
              AND r.request_date <= {marker}
            ORDER BY r.request_date ASC, r.created_at ASC
        """
        all_month_requests = connection.execute(unposted_query, (start_date, end_date)).fetchall()

        unposted_requests = []
        pending_approvals = []
        rejected_requests = []
        changes_requested = []

        for row in all_month_requests:
            req_dict = dict(row)
            req_dict["amount"] = float(row["amount"])
            req_status = row["status"]

            if req_status in {"DRAFT", "SUBMITTED", "APPROVED", "SUPPORTING_UPLOADED"}:
                unposted_requests.append(req_dict)
            if req_status == "SUBMITTED":
                pending_approvals.append(req_dict)
            elif req_status == "REJECTED":
                rejected_requests.append(req_dict)
            elif req_status == "DRAFT" and row["change_reason"]:
                changes_requested.append(req_dict)

        # Build project pivot and statement breakdowns identical to Spreadsheet Utility
        pivot_dict = {}
        for entry in posted_entries:
            proj = (entry.get("project") or "General").strip() or "General"
            if proj not in pivot_dict:
                pivot_dict[proj] = {
                    "sum_receipt": Decimal("0.00"),
                    "sum_payment": Decimal("0.00"),
                    "receipt_count": 0,
                    "payment_count": 0,
                }
            r_amt = Decimal(str(entry.get("receipt") or "0.00"))
            p_amt = Decimal(str(entry.get("payment") or "0.00"))
            if r_amt > 0:
                pivot_dict[proj]["sum_receipt"] += r_amt
                pivot_dict[proj]["receipt_count"] += 1
            if p_amt > 0:
                pivot_dict[proj]["sum_payment"] += p_amt
                pivot_dict[proj]["payment_count"] += 1

        pivot_rows = []
        for proj in sorted(pivot_dict.keys()):
            s_rec = float(pivot_dict[proj]["sum_receipt"])
            s_pay = float(pivot_dict[proj]["sum_payment"])
            pivot_rows.append({
                "project": proj,
                "sum_receipt": round(s_rec, 2) if s_rec > 0 else None,
                "sum_payment": round(s_pay, 2) if s_pay > 0 else None,
                "receipt_count": pivot_dict[proj]["receipt_count"],
                "payment_count": pivot_dict[proj]["payment_count"],
            })

        additions = []
        for proj in sorted(pivot_dict.keys()):
            rec_val = float(pivot_dict[proj]["sum_receipt"])
            if rec_val > 0:
                label = proj
                if proj.startswith("Petty Cash - "):
                    label = proj.replace("Petty Cash - ", "")
                additions.append({
                    "particular": label,
                    "project": proj,
                    "amount": round(rec_val, 2),
                    "count": pivot_dict[proj]["receipt_count"],
                })

        withdrawals = []
        for proj in sorted(pivot_dict.keys()):
            pay_val = float(pivot_dict[proj]["sum_payment"])
            if pay_val > 0:
                withdrawals.append({
                    "particular": proj,
                    "project": proj,
                    "amount": round(pay_val, 2),
                    "count": pivot_dict[proj]["payment_count"],
                })

        result_data = {
            "month": month_str,
            "month_name": month_name,
            "year": year,
            "start_date": start_date,
            "end_date": end_date,
            "opening_balance": float(opening_balance),
            "closing_balance": float(closing_balance),
            "total_receipts": float(total_receipts),
            "total_payments": float(total_payments),
            "net_movement": float(net_movement),
            "posted_count": len(posted_entries),
            "posted_entries": posted_entries,
            "daily_movement": daily_movement,
            "pivot_rows": pivot_rows,
            "additions": additions,
            "withdrawals": withdrawals,
            "company_receipts": [e for e in posted_entries if e.get("receipt") is not None],
            "receipts_by_ledger": list(receipt_ledger_breakdown_dict.values()),
            "receipts_by_project": list(receipt_project_breakdown_dict.values()),
            "spending_by_ledger": list(ledger_breakdown_dict.values()),
            "spending_by_category": list(category_breakdown_dict.values()),
            "spending_by_project": list(project_breakdown_dict.values()),
            "unposted_requests": unposted_requests,
            "pending_approvals_count": len(pending_approvals),
            "pending_approvals_total": sum(r["amount"] for r in pending_approvals),
            "rejected_count": len(rejected_requests),
            "rejected_total": sum(r["amount"] for r in rejected_requests),
            "changes_requested_count": len(changes_requested),
            "changes_requested_total": sum(r["amount"] for r in changes_requested),
            "all_supporting_files": all_supporting_files,
        }
        if not is_testing:
            _REPORT_CACHE[cache_key] = (time.time(), result_data)
        return result_data


def _accumulate_breakdown(target_dict: dict, key: str, amount: Decimal):
    clean_key = (key or "Unassigned").strip()
    if clean_key not in target_dict:
        target_dict[clean_key] = {"name": clean_key, "amount": float(amount), "count": 1}
    else:
        target_dict[clean_key]["amount"] = round(target_dict[clean_key]["amount"] + float(amount), 2)
        target_dict[clean_key]["count"] += 1


# ─── Standardized 12-Column Excel Generation ─────────────────────────────────

def generate_monthly_excel(
    report_data: Dict[str, Any],
    relative_supporting_prefix: Optional[str] = None,
    web_base_url: Optional[str] = None,
) -> io.BytesIO:
    """Generate professional 3-sheet workbook strictly adhering to the 12-column schema.
    
    Sheets:
    1. 'Petty Cash Sheet' (Exact 12 columns with primary supporting hyperlink)
    2. 'Petty Cash Summary' (Authoritative balances, KPI totals, and reconciliation breakdowns)
    3. 'Supporting Files' (Catalog of all uploaded files with direct relative hyperlinks)
    """
    wb = openpyxl.Workbook()

    # 1. Sheet 1: Petty Cash Summary (matches layout and drill-down links of Spreadsheet Utility)
    ws_sum = wb.active
    ws_sum.title = "Petty Cash Summary"
    ws_sum.views.sheetView[0].showGridLines = True

    # 2. Sheet 2: Petty Cash Sheet (Exact 12 columns with primary supporting hyperlink)
    ws_tx = wb.create_sheet(title="Petty Cash Sheet")
    ws_tx.views.sheetView[0].showGridLines = True

    # Header Row
    for col_idx, col_name in enumerate(REQUIRED_12_COLUMNS, start=1):
        cell = ws_tx.cell(1, col_idx, col_name)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = Alignment(horizontal="center" if col_idx in [1, 4, 5, 6, 7, 8] else "left", vertical="center")
        cell.border = BORDER_ALL_THIN
    ws_tx.row_dimensions[1].height = 24

    # Data Rows
    posted_entries = report_data.get("posted_entries", [])
    for row_idx, item in enumerate(posted_entries, start=2):
        ws_tx.cell(row_idx, 1, item.get("date", ""))
        ws_tx.cell(row_idx, 2, item.get("ledger", ""))
        ws_tx.cell(row_idx, 3, item.get("description", ""))
        ws_tx.cell(row_idx, 4, item.get("receipt"))
        ws_tx.cell(row_idx, 5, item.get("payment"))
        ws_tx.cell(row_idx, 6, item.get("outstanding_balance", 0.0))
        ws_tx.cell(row_idx, 7, item.get("approved_by", ""))
        ws_tx.cell(row_idx, 8, item.get("requested_by", ""))
        ws_tx.cell(row_idx, 9, item.get("category", ""))
        ws_tx.cell(row_idx, 10, item.get("project", ""))

        # Primary supporting file hyperlink
        sup_cell = ws_tx.cell(row_idx, 11, item.get("supportings", ""))
        sup_files = item.get("all_supportings", [])
        if sup_files and relative_supporting_prefix:
            first_file = sup_files[0]
            clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", first_file["original_filename"])
            safe_archive_name = f"{item.get('request_id', 'req')[:8]}_{clean_name}"
            sup_cell.value = f'=HYPERLINK("{relative_supporting_prefix}/{safe_archive_name}", "{first_file["original_filename"]}")'
            sup_cell.hyperlink = f"{relative_supporting_prefix}/{safe_archive_name}"
            sup_cell.font = FONT_LINK
        elif sup_files and web_base_url:
            first_file = sup_files[0]
            download_url = f"{web_base_url.rstrip('/')}/api/supporting-files/{first_file['id']}/download"
            sup_cell.value = f'=HYPERLINK("{download_url}", "{first_file["original_filename"]}")'
            sup_cell.hyperlink = download_url
            sup_cell.font = FONT_LINK

        ws_tx.cell(row_idx, 12, item.get("notes", ""))

        # Styling
        zebra = (row_idx % 2 == 1)
        for c in range(1, 13):
            cell = ws_tx.cell(row_idx, c)
            if not (c == 11 and sup_files and (relative_supporting_prefix or web_base_url)):
                cell.font = FONT_REGULAR
            cell.border = BORDER_ALL_THIN
            if zebra and cell.fill.fill_type is None:
                cell.fill = FILL_ZEBRA

            if c == 1:
                cell.alignment = Alignment(horizontal="center")
            elif c in [4, 5, 6]:
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = "#,##0.00"
            else:
                cell.alignment = Alignment(horizontal="left")

    # Column Widths
    col_widths = {
        "A": 12, "B": 20, "C": 40, "D": 14, "E": 14,
        "F": 18, "G": 16, "H": 16, "I": 22, "J": 26,
        "K": 28, "L": 30,
    }
    for col_letter, width in col_widths.items():
        ws_tx.column_dimensions[col_letter].width = width

    # Left Pivot Table: Columns A to C
    ws_sum.cell(3, 1, "Row Labels").font = FONT_BOLD
    ws_sum.cell(3, 2, "Sum of Receipt").font = FONT_BOLD
    ws_sum.cell(3, 3, "Sum of Payment").font = FONT_BOLD

    for c in range(1, 4):
        ws_sum.cell(3, c).border = BORDER_ALL_THIN
        ws_sum.cell(3, c).alignment = Alignment(horizontal="left" if c == 1 else "right")
        ws_sum.cell(3, c).fill = FILL_HIGHLIGHT

    pivot_rows = report_data.get("pivot_rows", [])
    drilldown_sheets = {}

    def add_drilldown_link(cell, project: str, tx_type: str):
        sheet = drilldown_sheets.get((project, tx_type))
        if sheet:
            cell.hyperlink = Hyperlink(
                ref=cell.coordinate,
                location=f"'{sheet.title}'!A1",
            )

    def create_drilldown_sheet(project: str, tx_type: str):
        key = (project, tx_type)
        if key in drilldown_sheets:
            return drilldown_sheets[key]

        rows = [
            tx for tx in posted_entries
            if (project == "Grand Total" or ((tx.get("project") or "General").strip() or "General") == project)
            and (float(tx.get(tx_type, 0) or 0) > 0)
        ]
        suffix = "Receipts" if tx_type == "receipt" else "Payments"
        base_title = re.sub(r"[:\\/?*\[\]]", "-", f"Details - {project[:18]} - {suffix}")
        title = base_title[:31]
        existing_titles = {sheet.title for sheet in wb.worksheets}
        counter = 2
        while title in existing_titles:
            suffix_number = f" ({counter})"
            title = f"{base_title[:31 - len(suffix_number)]}{suffix_number}"
            counter += 1

        sheet = wb.create_sheet(title=title)
        sheet.views.sheetView[0].showGridLines = True
        sheet.merge_cells("A1:J1")
        title_cell = sheet.cell(1, 1, f"Background Transactions: {project} ({tx_type.upper()})")
        title_cell.font = FONT_TITLE_WHITE
        title_cell.fill = HEADER_BLUE_FILL
        title_cell.alignment = Alignment(horizontal="center", vertical="center")

        headers = [
            "Date", "Ledger", "Memo / Description", "Receipt", "Payment",
            "Outstanding Balance", "Approved", "Requested By", "Category", "Project"
        ]
        for col_idx, header in enumerate(headers, start=1):
            header_cell = sheet.cell(2, col_idx, header)
            header_cell.font = FONT_HEADER
            header_cell.fill = YELLOW_FILL
            header_cell.border = BORDER_ALL_THIN

        for row_idx, tx in enumerate(rows, start=3):
            values = [
                tx.get("date", ""),
                tx.get("ledger", ""),
                tx.get("description") or tx.get("memo", ""),
                tx.get("receipt") or None,
                tx.get("payment") or None,
                tx.get("outstanding_balance", 0.0),
                tx.get("approved_by") or tx.get("approved", ""),
                tx.get("requested_by", ""),
                tx.get("category", ""),
                tx.get("project", ""),
            ]
            for col_idx, value in enumerate(values, start=1):
                detail_cell = sheet.cell(row_idx, col_idx, value)
                detail_cell.font = FONT_REGULAR
                detail_cell.border = BORDER_ALL_THIN
                if col_idx in [4, 5, 6]:
                    detail_cell.number_format = "#,##0.00"

        total_row = len(rows) + 3
        sheet.cell(total_row, 1, "Total").font = FONT_BOLD
        sheet.cell(total_row, 1).border = BORDER_ALL_THIN
        for col_idx in range(2, 4):
            sheet.cell(total_row, col_idx).border = BORDER_ALL_THIN
        for col_idx, field in ((4, "receipt"), (5, "payment")):
            tot_val = sum(float(tx.get(field, 0) or 0) for tx in rows)
            total_cell = sheet.cell(total_row, col_idx, tot_val or "")
            total_cell.font = FONT_BOLD
            total_cell.border = BORDER_ALL_THIN
            total_cell.number_format = "#,##0.00"
        for col_idx in range(6, 11):
            sheet.cell(total_row, col_idx).border = BORDER_ALL_THIN

        for col_letter, width in {
            "A": 14, "B": 20, "C": 48, "D": 16, "E": 16,
            "F": 18, "G": 16, "H": 16, "I": 24, "J": 28,
        }.items():
            sheet.column_dimensions[col_letter].width = width

        drilldown_sheets[key] = sheet
        return sheet

    for prow in pivot_rows:
        project = prow["project"]
        if prow.get("sum_receipt"):
            create_drilldown_sheet(project, "receipt")
        if prow.get("sum_payment"):
            create_drilldown_sheet(project, "payment")
    create_drilldown_sheet("Grand Total", "receipt")
    create_drilldown_sheet("Grand Total", "payment")

    curr_pivot_row = 4
    for prow in pivot_rows:
        ws_sum.cell(curr_pivot_row, 1, prow["project"]).font = FONT_REGULAR
        ws_sum.cell(curr_pivot_row, 1).border = BORDER_ALL_THIN

        c_rec = ws_sum.cell(curr_pivot_row, 2, prow.get("sum_receipt") or "")
        c_rec.font = FONT_REGULAR
        c_rec.border = BORDER_ALL_THIN
        c_rec.number_format = "#,##0.00"
        if prow.get("sum_receipt"):
            add_drilldown_link(c_rec, prow["project"], "receipt")

        c_pay = ws_sum.cell(curr_pivot_row, 3, prow.get("sum_payment") or "")
        c_pay.font = FONT_REGULAR
        c_pay.border = BORDER_ALL_THIN
        c_pay.number_format = "#,##0.00"
        if prow.get("sum_payment"):
            add_drilldown_link(c_pay, prow["project"], "payment")

        curr_pivot_row += 1

    # Pivot Grand Total
    ws_sum.cell(curr_pivot_row, 1, "Grand Total").font = FONT_BOLD
    ws_sum.cell(curr_pivot_row, 1).border = BORDER_ALL_THIN

    tot_rec_cell = ws_sum.cell(curr_pivot_row, 2, f"=SUM(B4:B{curr_pivot_row - 1})" if curr_pivot_row > 4 else 0)
    tot_rec_cell.font = FONT_BOLD
    tot_rec_cell.border = BORDER_ALL_THIN
    tot_rec_cell.number_format = "#,##0.00"
    add_drilldown_link(tot_rec_cell, "Grand Total", "receipt")

    tot_pay_cell = ws_sum.cell(curr_pivot_row, 3, f"=SUM(C4:C{curr_pivot_row - 1})" if curr_pivot_row > 4 else 0)
    tot_pay_cell.font = FONT_BOLD
    tot_pay_cell.border = BORDER_ALL_THIN
    tot_pay_cell.number_format = "#,##0.00"
    add_drilldown_link(tot_pay_cell, "Grand Total", "payment")

    # Right Reconciliation Statement: Columns I to K
    ws_sum.merge_cells("I2:K2")
    title_cell = ws_sum.cell(2, 9, "Petty Cash Summary")
    title_cell.font = FONT_TITLE_WHITE
    title_cell.fill = HEADER_BLUE_FILL
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    for c in range(9, 12):
        ws_sum.cell(2, c).border = BORDER_ALL_THIN

    ws_sum.cell(3, 9, "Particulares").font = FONT_TITLE_WHITE
    ws_sum.cell(3, 9).fill = HEADER_BLUE_FILL
    ws_sum.cell(3, 9).border = BORDER_ALL_THIN

    ws_sum.cell(3, 10, "Amount").font = FONT_TITLE_WHITE
    ws_sum.cell(3, 10).fill = HEADER_BLUE_FILL
    ws_sum.cell(3, 10).border = BORDER_ALL_THIN

    ws_sum.cell(3, 11, "Amount").font = FONT_TITLE_WHITE
    ws_sum.cell(3, 11).fill = HEADER_BLUE_FILL
    ws_sum.cell(3, 11).border = BORDER_ALL_THIN

    # Opening balance
    ws_sum.cell(4, 9, "Petty Cash Opening Balance").font = FONT_REGULAR
    ws_sum.cell(4, 9).border = BORDER_ALL_THIN
    ws_sum.cell(4, 10, "").border = BORDER_ALL_THIN
    op_cell = ws_sum.cell(4, 11, report_data.get("opening_balance", 0.0))
    op_cell.font = FONT_REGULAR
    op_cell.border = BORDER_ALL_THIN
    op_cell.number_format = "#,##0.00"

    start_date_str = report_data.get("start_date", "")
    ws_sum.cell(5, 9, f"({start_date_str})" if start_date_str else "").font = FONT_REGULAR
    ws_sum.cell(5, 9).border = BORDER_ALL_THIN
    ws_sum.cell(5, 10, "").border = BORDER_ALL_THIN
    ws_sum.cell(5, 11, "").border = BORDER_ALL_THIN

    for c in range(9, 12):
        ws_sum.cell(6, c).border = BORDER_ALL_THIN

    ws_sum.cell(7, 9, "Additions").font = FONT_BOLD
    ws_sum.cell(7, 9).fill = YELLOW_FILL
    ws_sum.cell(7, 9).border = BORDER_ALL_THIN
    ws_sum.cell(7, 10, "").border = BORDER_ALL_THIN

    additions = report_data.get("additions", [])
    add_start_row = 8
    curr_add_row = add_start_row
    for item in additions:
        ws_sum.cell(curr_add_row, 9, item["particular"]).font = FONT_REGULAR
        ws_sum.cell(curr_add_row, 9).border = BORDER_ALL_THIN

        amt_c = ws_sum.cell(curr_add_row, 10, item["amount"])
        amt_c.font = FONT_REGULAR
        amt_c.border = BORDER_ALL_THIN
        amt_c.number_format = "#,##0.00"
        add_drilldown_link(amt_c, item["project"], "receipt")

        ws_sum.cell(curr_add_row, 11, "").border = BORDER_ALL_THIN
        curr_add_row += 1

    add_end_row = curr_add_row - 1 if additions else 8
    add_sum_cell = ws_sum.cell(7, 11, f"=+SUM(J{add_start_row}:J{add_end_row})" if additions else 0)
    add_sum_cell.font = FONT_BOLD
    add_sum_cell.border = BORDER_ALL_THIN
    add_sum_cell.number_format = "#,##0.00"
    add_drilldown_link(add_sum_cell, "Grand Total", "receipt")

    # Withdrawals
    withdraw_hdr_row = curr_add_row
    ws_sum.cell(withdraw_hdr_row, 9, "Withdraw").font = FONT_BOLD
    ws_sum.cell(withdraw_hdr_row, 9).fill = YELLOW_FILL
    ws_sum.cell(withdraw_hdr_row, 9).border = BORDER_ALL_THIN
    ws_sum.cell(withdraw_hdr_row, 10, "").border = BORDER_ALL_THIN

    withdrawals = report_data.get("withdrawals", [])
    w_start_row = withdraw_hdr_row + 1
    curr_w_row = w_start_row
    for item in withdrawals:
        ws_sum.cell(curr_w_row, 9, item["particular"]).font = FONT_REGULAR
        ws_sum.cell(curr_w_row, 9).border = BORDER_ALL_THIN

        amt_c = ws_sum.cell(curr_w_row, 10, item["amount"])
        amt_c.font = FONT_REGULAR
        amt_c.border = BORDER_ALL_THIN
        amt_c.number_format = "#,##0.00"
        add_drilldown_link(amt_c, item["project"], "payment")

        ws_sum.cell(curr_w_row, 11, "").border = BORDER_ALL_THIN
        curr_w_row += 1

    w_end_row = curr_w_row - 1 if withdrawals else w_start_row
    w_sum_cell = ws_sum.cell(withdraw_hdr_row, 11, f"=-SUM(J{w_start_row}:J{w_end_row})" if withdrawals else 0)
    w_sum_cell.font = FONT_BOLD
    w_sum_cell.border = BORDER_ALL_THIN
    w_sum_cell.number_format = "#,##0.00"
    add_drilldown_link(w_sum_cell, "Grand Total", "payment")

    # Spacer rows before closing balance
    spacer_row = curr_w_row
    for c in range(9, 12):
        ws_sum.cell(spacer_row, c).border = BORDER_ALL_THIN
    spacer_row2 = spacer_row + 1
    for c in range(9, 12):
        ws_sum.cell(spacer_row2, c).border = BORDER_ALL_THIN

    closing_row = spacer_row2 + 1
    end_date_str = report_data.get("end_date", "")
    closing_label = f"Closing balance as on {end_date_str}" if end_date_str else "Closing balance"
    ws_sum.cell(closing_row, 9, closing_label).font = FONT_BOLD
    ws_sum.cell(closing_row, 9).border = BORDER_ALL_THIN
    ws_sum.cell(closing_row, 10, "").border = BORDER_ALL_THIN

    closing_cell = ws_sum.cell(closing_row, 11, f"=+SUM(K4:K{closing_row - 1})")
    closing_cell.font = FONT_BOLD
    closing_cell.border = BORDER_ALL_THIN
    closing_cell.number_format = "#,##0.00"

    # Set Column Widths for Petty Cash Summary (identical to excel_service.py)
    summary_col_widths = {
        "A": 32, "B": 16, "C": 16, "D": 5, "E": 5, "F": 5, "G": 5, "H": 5,
        "I": 40, "J": 16, "K": 18
    }
    for col_letter, width in summary_col_widths.items():
        ws_sum.column_dimensions[col_letter].width = width

    # 3. Sheet 3: Supporting Files
    ws_sup = wb.create_sheet(title="Supporting Files")
    ws_sup.views.sheetView[0].showGridLines = True

    sup_headers = [
        "Request ID", "Date", "Requested By", "Description",
        "Original Filename", "File Link", "Size (Bytes)", "Uploaded At"
    ]
    for c_idx, h in enumerate(sup_headers, start=1):
        cell = ws_sup.cell(1, c_idx, h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.border = BORDER_ALL_THIN
        cell.alignment = Alignment(horizontal="left", vertical="center")
    ws_sup.row_dimensions[1].height = 24

    sup_row_idx = 2
    for entry in posted_entries:
        req_id = entry.get("request_id")
        if not req_id:
            continue
        for f in entry.get("all_supportings", []):
            clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", f["original_filename"])
            safe_archive_name = f"{req_id[:8]}_{clean_name}"
            ws_sup.cell(sup_row_idx, 1, req_id)
            ws_sup.cell(sup_row_idx, 2, entry.get("date", ""))
            ws_sup.cell(sup_row_idx, 3, entry.get("requested_by", ""))
            ws_sup.cell(sup_row_idx, 4, entry.get("description", ""))
            ws_sup.cell(sup_row_idx, 5, f["original_filename"])

            link_cell = ws_sup.cell(sup_row_idx, 6, safe_archive_name)
            if relative_supporting_prefix:
                link_cell.value = f'=HYPERLINK("{relative_supporting_prefix}/{safe_archive_name}", "{f["original_filename"]}")'
                link_cell.hyperlink = f"{relative_supporting_prefix}/{safe_archive_name}"
                link_cell.font = FONT_LINK
            elif web_base_url:
                download_url = f"{web_base_url.rstrip('/')}/api/supporting-files/{f['id']}/download"
                link_cell.value = f'=HYPERLINK("{download_url}", "{f["original_filename"]}")'
                link_cell.hyperlink = download_url
                link_cell.font = FONT_LINK
            else:
                link_cell.font = FONT_REGULAR

            ws_sup.cell(sup_row_idx, 7, f["size_bytes"])
            ws_sup.cell(sup_row_idx, 8, f["created_at"])

            for c in range(1, 9):
                cell = ws_sup.cell(sup_row_idx, c)
                cell.border = BORDER_ALL_THIN
                if c != 6:
                    cell.font = FONT_REGULAR
            sup_row_idx += 1

    for col_letter, width in {"A": 22, "B": 12, "C": 16, "D": 36, "E": 28, "F": 32, "G": 14, "H": 22}.items():
        ws_sup.column_dimensions[col_letter].width = width

    # Ensure Petty Cash Summary is the primary active worksheet upon opening
    wb.active = ws_sum

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _generate_evidence_html(report_data: dict) -> str:
    month = report_data.get("month", "")
    op_bal = f"₹{report_data.get('opening_balance', 0):,.2f}"
    tot_rec = f"₹{report_data.get('total_receipts', 0):,.2f}"
    tot_pay = f"₹{report_data.get('total_payments', 0):,.2f}"
    cl_bal = f"₹{report_data.get('closing_balance', 0):,.2f}"

    rows_html = []
    for item in report_data.get("posted_entries", []):
        req_id = item.get("request_id") or ""
        sup_links = []
        for f in item.get("all_supportings", []):
            clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", f["original_filename"])
            safe_name = f"{req_id[:8]}_{clean_name}"
            sup_links.append(f'<a class="btn" href="supportings/{safe_name}" target="_blank">📄 {f["original_filename"]}</a>')

        sup_html = " ".join(sup_links) if sup_links else '<span class="muted">—</span>'
        rec_str = f"+₹{item['receipt']:,.2f}" if item.get("receipt") is not None else "—"
        pay_str = f"-₹{item['payment']:,.2f}" if item.get("payment") is not None else "—"
        bal_str = f"₹{item.get('outstanding_balance', 0):,.2f}"

        rows_html.append(f"""
        <tr>
            <td class="mono">{item.get('date', '')}</td>
            <td>{item.get('ledger', '')}</td>
            <td><strong>{item.get('description', '')}</strong></td>
            <td>{item.get('project', '')}</td>
            <td class="mono rec">{rec_str}</td>
            <td class="mono pay">{pay_str}</td>
            <td class="mono"><strong>{bal_str}</strong></td>
            <td>{sup_html}</td>
        </tr>
        """)

    tbody_content = "".join(rows_html) if rows_html else '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #94a3b8; font-size: 13px;">No posted transactions found for this reporting period.</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Petty Cash Audit Evidence Package - {month}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #020617; color: #e2e8f0; margin: 0; padding: 28px; line-height: 1.5; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
.header {{ border-bottom: 1px solid #1e293b; padding-bottom: 20px; margin-bottom: 24px; }}
h1 {{ font-size: 22px; font-weight: 700; color: #f8fafc; margin: 0 0 6px 0; }}
.sub {{ color: #94a3b8; font-size: 13px; }}
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 28px; }}
.kpi {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 16px 20px; }}
.kpi-label {{ font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 6px; }}
.kpi-val {{ font-size: 20px; font-weight: 700; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.rec {{ color: #34d399; }}
.pay {{ color: #fbbf24; }}
.card {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; overflow: hidden; }}
.card-header {{ padding: 14px 20px; background: #0b1120; border-bottom: 1px solid #1e293b; font-size: 13px; font-weight: 600; color: #cbd5e1; display: flex; justify-content: space-between; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th {{ background: #0b1120; color: #94a3b8; text-align: left; padding: 12px 14px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #1e293b; }}
td {{ padding: 12px 14px; border-bottom: 1px solid rgba(30, 41, 59, 0.6); vertical-align: middle; }}
tr:hover {{ background: rgba(30, 41, 59, 0.4); }}
.btn {{ display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; background: #065f46; color: #a7f3d0; text-decoration: none; border-radius: 4px; font-weight: 600; font-size: 11px; border: 1px solid #047857; }}
.btn:hover {{ background: #047857; color: #ffffff; }}
.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.muted {{ color: #475569; }}
.footer {{ margin-top: 24px; text-align: center; color: #475569; font-size: 11px; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>Petty Cash Audit Evidence Package — {month}</h1>
        <div class="sub">Reconciled Monthly Ledger, Canonical Records & Attached Voucher Evidence Files</div>
    </div>
    <div class="kpis">
        <div class="kpi"><div class="kpi-label">Opening Balance</div><div class="kpi-val">{op_bal}</div></div>
        <div class="kpi"><div class="kpi-label">Total Inbound Receipts</div><div class="kpi-val rec">{tot_rec}</div></div>
        <div class="kpi"><div class="kpi-label">Total Posted Payments</div><div class="kpi-val pay">{tot_pay}</div></div>
        <div class="kpi"><div class="kpi-label">Closing Vault Balance</div><div class="kpi-val">{cl_bal}</div></div>
    </div>
    <div class="card">
        <div class="card-header">
            <span>Monthly Transactions & Attached Voucher Evidences</span>
            <span>Click any voucher button to open the document</span>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Ledger</th>
                    <th>Memo / Description</th>
                    <th>Project</th>
                    <th>Receipt</th>
                    <th>Payment</th>
                    <th>Balance</th>
                    <th>Voucher Document</th>
                </tr>
            </thead>
            <tbody>
                {tbody_content}
            </tbody>
        </table>
    </div>
    <div class="footer">
        Generated by PettyCash Pro v2.0 • Canonical Ledger System • Hyperlinks resolve to local supportings/ directory
    </div>
</div>
</body>
</html>"""


# ─── Monthly ZIP Bundle Generation ───────────────────────────────────────────

def generate_monthly_zip_bundle(month_str: str) -> io.BytesIO:
    """Generate complete monthly ZIP package containing the workbook and all supporting documents.
    
    Structure of ZIP:
    ├── Petty_Cash_Report_YYYY_MM.xlsx
    ├── evidence_viewer.html
    └── supportings/
        ├── req12345_bill1.pdf
        └── req67890_receipt.png
    """
    report_data = get_monthly_report_data(month_str)
    zip_buffer = io.BytesIO()
    root_dir = storage_root()

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        # 1. Add supporting files to supportings/
        for entry in report_data.get("posted_entries", []):
            req_id = entry.get("request_id")
            if not req_id:
                continue
            for f in entry.get("all_supportings", []):
                file_disk_path = root_dir / f["storage_key"]
                clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", f["original_filename"])
                safe_archive_name = f"{req_id[:8]}_{clean_name}"
                archive_path = f"supportings/{safe_archive_name}"

                file_bytes = None
                if file_disk_path.is_file():
                    file_bytes = file_disk_path.read_bytes()
                elif f.get("file_data"):
                    try:
                        file_bytes = base64.b64decode(f["file_data"])
                        file_disk_path.parent.mkdir(parents=True, exist_ok=True)
                        file_disk_path.write_bytes(file_bytes)
                    except Exception:
                        file_bytes = None

                if not file_bytes:
                    with database.get_connection() as conn:
                        marker = database._placeholder()
                        f_row = conn.execute(
                            f"SELECT file_data FROM supporting_files WHERE id={marker}",
                            (f["id"],),
                        ).fetchone()
                        if f_row and f_row.get("file_data"):
                            try:
                                file_bytes = base64.b64decode(f_row["file_data"])
                                file_disk_path.parent.mkdir(parents=True, exist_ok=True)
                                file_disk_path.write_bytes(file_bytes)
                            except Exception:
                                file_bytes = None

                if file_bytes:
                    archive.writestr(archive_path, file_bytes)

        # 2. Add Excel workbook with relative links pointing to supportings/
        excel_stream = generate_monthly_excel(report_data, relative_supporting_prefix="supportings")
        workbook_filename = f"Petty_Cash_Report_{report_data['month'].replace('-', '_')}.xlsx"
        archive.writestr(workbook_filename, excel_stream.getvalue())

        # 3. Add offline Evidence Viewer HTML
        html_report = _generate_evidence_html(report_data)
        archive.writestr("evidence_viewer.html", html_report.encode("utf-8"))

    zip_buffer.seek(0)
    return zip_buffer


# ─── Legacy Ledger Standardized 12-Column Export ─────────────────────────────

def generate_legacy_12col_excel(session_data: dict) -> io.BytesIO:
    """Export an isolated legacy session strictly matching the standardized 12-column schema."""
    wb = openpyxl.Workbook()
    ws_tx = wb.active
    ws_tx.title = "Petty Cash Sheet"
    ws_tx.views.sheetView[0].showGridLines = True

    # Header Row
    for col_idx, col_name in enumerate(REQUIRED_12_COLUMNS, start=1):
        cell = ws_tx.cell(1, col_idx, col_name)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = Alignment(horizontal="center" if col_idx in [1, 4, 5, 6, 7, 8] else "left", vertical="center")
        cell.border = BORDER_ALL_THIN
    ws_tx.row_dimensions[1].height = 24

    transactions = session_data.get("transactions", [])
    opening_balance = float(session_data.get("opening_balance", 0.0))
    running_balance = opening_balance

    for row_idx, tx in enumerate(transactions, start=2):
        rec = float(tx.get("receipt", 0.0) or 0.0)
        pay = float(tx.get("payment", 0.0) or 0.0)
        running_balance = running_balance + rec - pay

        ws_tx.cell(row_idx, 1, tx.get("date", ""))
        ws_tx.cell(row_idx, 2, tx.get("ledger", ""))
        ws_tx.cell(row_idx, 3, tx.get("memo") or tx.get("description", ""))
        ws_tx.cell(row_idx, 4, rec if rec > 0 else None)
        ws_tx.cell(row_idx, 5, pay if pay > 0 else None)
        ws_tx.cell(row_idx, 6, running_balance)
        ws_tx.cell(row_idx, 7, tx.get("approved") or tx.get("approved_by", ""))
        ws_tx.cell(row_idx, 8, tx.get("requested_by", ""))
        ws_tx.cell(row_idx, 9, tx.get("category", ""))
        ws_tx.cell(row_idx, 10, tx.get("project", ""))

        sups = tx.get("supportings", [])
        if isinstance(sups, list):
            sup_str = ", ".join(item.get("name", str(item)) if isinstance(item, dict) else str(item) for item in sups)
        else:
            sup_str = str(sups) if sups else ""
        ws_tx.cell(row_idx, 11, sup_str)
        ws_tx.cell(row_idx, 12, tx.get("notes", ""))

        for c in range(1, 13):
            cell = ws_tx.cell(row_idx, c)
            cell.font = FONT_REGULAR
            cell.border = BORDER_ALL_THIN
            if c == 1:
                cell.alignment = Alignment(horizontal="center")
            elif c in [4, 5, 6]:
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = "#,##0.00"
            else:
                cell.alignment = Alignment(horizontal="left")

    col_widths = {
        "A": 12, "B": 20, "C": 40, "D": 14, "E": 14,
        "F": 18, "G": 16, "H": 16, "I": 22, "J": 26,
        "K": 28, "L": 30,
    }
    for col_letter, width in col_widths.items():
        ws_tx.column_dimensions[col_letter].width = width

    # Add Summary Sheet
    ws_sum = wb.create_sheet(title="Petty Cash Summary")
    ws_sum.views.sheetView[0].showGridLines = True
    ws_sum.cell(1, 1, f"Legacy Session — {session_data.get('name', 'Petty Cash')}").font = FONT_TITLE
    ws_sum.cell(2, 1, f"Period: {session_data.get('start_date', '')} to {session_data.get('end_date', '')}").font = FONT_SUBTITLE

    total_rec = sum(float(t.get("receipt", 0.0) or 0.0) for t in transactions)
    total_pay = sum(float(t.get("payment", 0.0) or 0.0) for t in transactions)

    metrics = [
        ("Opening Balance", opening_balance),
        ("Total Receipts", total_rec),
        ("Total Payments", total_pay),
        ("Net Movement", total_rec - total_pay),
        ("Closing Balance", running_balance),
    ]
    for idx, (lbl, val) in enumerate(metrics, start=4):
        c1 = ws_sum.cell(idx, 1, lbl)
        c2 = ws_sum.cell(idx, 2, val)
        c1.font = FONT_BOLD
        c2.font = FONT_BOLD
        c1.border = BORDER_ALL_THIN
        c2.border = BORDER_ALL_THIN
        c2.number_format = "₹#,##0.00"
        c2.alignment = Alignment(horizontal="right")

    ws_sum.column_dimensions["A"].width = 25
    ws_sum.column_dimensions["B"].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
