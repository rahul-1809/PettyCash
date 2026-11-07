import io
import os
import datetime
from typing import List, Dict, Any, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import openpyxl.utils.datetime as opydt

# Common style constants matching the reference template
THIN_SIDE = Side(border_style="thin", color="000000")
ALL_THIN_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

YELLOW_FILL = PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")
HEADER_BLUE_FILL = PatternFill(start_color="FF4F81BD", end_color="FF4F81BD", fill_type="solid")
LIGHT_BLUE_FILL = PatternFill(start_color="FFDCE6F1", end_color="FFDCE6F1", fill_type="solid")

FONT_HEADER = Font(name="Calibri", size=10, bold=True, color="000000")
FONT_TITLE_WHITE = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
FONT_REGULAR = Font(name="Calibri", size=10, bold=False, color="000000")
FONT_BOLD = Font(name="Calibri", size=10, bold=True, color="000000")

DEFAULT_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "RTEAM -Petty Cash Sheet -  01.10.2026-06.11.2026.xlsx"
)


def format_date_str(val: Any) -> str:
    """
    Safely converts any date value (datetime, Excel serial number like 46296, or formatted string)
    into standard 'YYYY-MM-DD' string.
    """
    if val is None or str(val).strip() == "":
        return ""
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime("%Y-%m-%d")

    # If numeric Excel serial number (e.g. 46296)
    if isinstance(val, (int, float)):
        try:
            return opydt.from_excel(val).strftime("%Y-%m-%d")
        except Exception:
            pass

    # If string that represents a numeric Excel serial number
    s = str(val).strip()
    try:
        f = float(s)
        if 20000 <= f <= 80000:
            return opydt.from_excel(f).strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Try common date formats
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(s.split("T")[0].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return s.split("T")[0].strip()


def parse_date_for_excel(val: Any) -> Any:
    """
    Converts a date string into a datetime.date object for native Excel cell storage.
    """
    if not val:
        return ""
    date_str = format_date_str(val)
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return date_str


def get_month_name(date_val: Any) -> str:
    """
    Extracts the full month name (e.g. 'October', 'November') from a date value.
    """
    if not date_val:
        return ""
    s = str(date_val).split("T")[0].strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%B")
        except ValueError:
            pass
    return ""


def parse_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").replace("₹", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_petty_cash_file(file_path_or_bytes) -> Dict[str, Any]:
    """
    Parses a Petty Cash workbook and extracts opening balance, dates, and transactions.
    """
    if isinstance(file_path_or_bytes, bytes):
        wb = openpyxl.load_workbook(io.BytesIO(file_path_or_bytes), data_only=True)
    elif hasattr(file_path_or_bytes, "read"):
        wb = openpyxl.load_workbook(file_path_or_bytes, data_only=True)
    else:
        wb = openpyxl.load_workbook(file_path_or_bytes, data_only=True)

    # Detect Petty Cash Sheet
    sheet_names = wb.sheetnames
    tx_sheet_name = next((s for s in sheet_names if "petty cash sheet" in s.lower()), sheet_names[0])
    tx_sheet = wb[tx_sheet_name]

    # Look for Summary Sheet to extract opening balance and dates
    summary_sheet_name = next((s for s in sheet_names if "summary" in s.lower()), None)
    opening_balance = None
    start_date = None
    end_date = None

    if summary_sheet_name:
        sum_sheet = wb[summary_sheet_name]
        for r in range(1, min(sum_sheet.max_row + 1, 30)):
            for c in range(1, min(sum_sheet.max_column + 1, 15)):
                val = sum_sheet.cell(r, c).value
                if val and "opening balance" in str(val).lower():
                    for offset in range(1, 5):
                        amt_cell = sum_sheet.cell(r, c + offset).value
                        if isinstance(amt_cell, (int, float)):
                            opening_balance = float(amt_cell)
                            break
                if val and str(val).startswith("(") and ("-" in str(val) or "." in str(val)):
                    cleaned = str(val).strip("() ")
                    start_date = format_date_str(cleaned)
                if val and "closing balance as on" in str(val).lower():
                    date_part = str(val).lower().replace("closing balance as on", "").strip()
                    if date_part:
                        end_date = format_date_str(date_part)

    # Read transaction rows
    transactions = []
    header_row = 1
    found_headers = False

    for r in range(1, min(tx_sheet.max_row + 1, 10)):
        row_vals = [str(tx_sheet.cell(r, c).value or "").strip().lower() for c in range(1, 11)]
        if any("date" in v for v in row_vals) and any("receipt" in v or "payment" in v for v in row_vals):
            header_row = r
            found_headers = True
            break

    start_data_row = header_row + 1 if found_headers else 2

    for r in range(start_data_row, tx_sheet.max_row + 1):
        d_val = tx_sheet.cell(r, 1).value
        ledger = tx_sheet.cell(r, 2).value
        memo = tx_sheet.cell(r, 3).value
        receipt = parse_float(tx_sheet.cell(r, 4).value)
        payment = parse_float(tx_sheet.cell(r, 5).value)
        balance = parse_float(tx_sheet.cell(r, 6).value)
        approved = tx_sheet.cell(r, 7).value
        requested_by = tx_sheet.cell(r, 8).value
        category = tx_sheet.cell(r, 9).value
        project = tx_sheet.cell(r, 10).value

        # Check if row is not empty
        if not d_val and not ledger and not memo and receipt == 0 and payment == 0:
            continue

        date_str = format_date_str(d_val)
        transactions.append({
            "id": f"tx-{r}",
            "date": date_str,
            "month": get_month_name(date_str),
            "ledger": str(ledger or "").strip(),
            "memo": str(memo or "").strip(),
            "receipt": receipt,
            "payment": payment,
            "balance": balance,
            "approved": str(approved or "").strip(),
            "requested_by": str(requested_by or "").strip(),
            "category": str(category or "").strip(),
            "project": str(project or "").strip(),
        })

    # If opening balance was not explicitly found in summary, infer from row 1
    if opening_balance is None and len(transactions) > 0:
        first_tx = transactions[0]
        opening_balance = round(first_tx["balance"] - first_tx["receipt"] + first_tx["payment"], 2)

    if not start_date and len(transactions) > 0:
        start_date = transactions[0]["date"]
    if not end_date and len(transactions) > 0:
        end_date = transactions[-1]["date"]

    summary_data = recalculate_summary(opening_balance or 0.0, start_date or "", end_date or "", transactions)

    return {
        "opening_balance": opening_balance or 0.0,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "transactions": transactions,
        "summary": summary_data,
    }


def recalculate_summary(opening_balance: float, start_date: str, end_date: str, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Recalculates running balances, pivot table, and cash reconciliation statement.
    """
    running_balance = opening_balance
    processed_txs = []

    for tx in transactions:
        receipt = parse_float(tx.get("receipt", 0))
        payment = parse_float(tx.get("payment", 0))
        running_balance = round(running_balance + receipt - payment, 2)
        d_str = format_date_str(tx.get("date", ""))

        processed_txs.append({
            **tx,
            "date": d_str,
            "month": tx.get("month") or get_month_name(d_str),
            "receipt": receipt,
            "payment": payment,
            "balance": running_balance,
        })

    # Aggregate by Project for Pivot Table
    pivot_dict = {}
    for tx in processed_txs:
        proj = tx.get("project", "").strip() or "Unassigned"
        if proj not in pivot_dict:
            pivot_dict[proj] = {"sum_receipt": 0.0, "sum_payment": 0.0, "receipt_count": 0, "payment_count": 0}
        if tx["receipt"] > 0:
            pivot_dict[proj]["sum_receipt"] += tx["receipt"]
            pivot_dict[proj]["receipt_count"] += 1
        if tx["payment"] > 0:
            pivot_dict[proj]["sum_payment"] += tx["payment"]
            pivot_dict[proj]["payment_count"] += 1

    pivot_rows = []
    total_receipts = 0.0
    total_payments = 0.0

    for proj in sorted(pivot_dict.keys()):
        s_rec = round(pivot_dict[proj]["sum_receipt"], 2)
        s_pay = round(pivot_dict[proj]["sum_payment"], 2)
        total_receipts += s_rec
        total_payments += s_pay
        pivot_rows.append({
            "project": proj,
            "sum_receipt": s_rec if s_rec > 0 else None,
            "sum_payment": s_pay if s_pay > 0 else None,
            "receipt_count": pivot_dict[proj]["receipt_count"],
            "payment_count": pivot_dict[proj]["payment_count"],
        })

    total_receipts = round(total_receipts, 2)
    total_payments = round(total_payments, 2)
    closing_balance = round(opening_balance + total_receipts - total_payments, 2)

    # Build Reconciliation Statement
    additions = []
    for proj in sorted(pivot_dict.keys()):
        rec_val = round(pivot_dict[proj]["sum_receipt"], 2)
        if rec_val > 0:
            label = proj
            if proj.startswith("Petty Cash - "):
                label = proj.replace("Petty Cash - ", "")
            elif proj == "Loan to N Employees":
                label = "Loan Reimbursed from Nomesh & Pallavi"
            elif proj == "NSP":
                label = "NSP - Deposit"
            elif proj == "Reimbursement - Nithin":
                label = "Reimbursement received - Nithin"

            additions.append({
                "particular": label,
                "project": proj,
                "amount": rec_val,
                "count": pivot_dict[proj]["receipt_count"]
            })

    withdrawals = []
    for proj in sorted(pivot_dict.keys()):
        pay_val = round(pivot_dict[proj]["sum_payment"], 2)
        if pay_val > 0:
            label = proj
            if proj == "NSP":
                label = "NSP - Travel"
            withdrawals.append({
                "particular": label,
                "project": proj,
                "amount": pay_val,
                "count": pivot_dict[proj]["payment_count"]
            })

    return {
        "opening_balance": opening_balance,
        "start_date": start_date,
        "end_date": end_date,
        "total_receipts": total_receipts,
        "total_payments": total_payments,
        "closing_balance": closing_balance,
        "pivot_rows": pivot_rows,
        "additions": additions,
        "withdrawals": withdrawals,
        "transactions": processed_txs,
    }


def generate_styled_excel(opening_balance: float, start_date: str, end_date: str, transactions: List[Dict[str, Any]]) -> io.BytesIO:
    """
    Generates a 2-sheet Excel file replicating the reference formatting, styling, formulas,
    and preserving native Excel PivotTable drill-down capability.
    """
    summary_data = recalculate_summary(opening_balance, start_date, end_date, transactions)
    tx_list = summary_data["transactions"]

    # If the template file is available, use it as the base so that native Excel PivotTable
    # and PivotCache relationships are preserved!
    use_template = os.path.exists(DEFAULT_TEMPLATE_PATH)

    if use_template:
        wb = openpyxl.load_workbook(DEFAULT_TEMPLATE_PATH)
        ws_tx = wb["Petty Cash Sheet"]
        ws_summary = wb["Petty Cash Summary "]

        # Clear existing rows in Petty Cash Sheet from row 2 onwards
        for r in range(2, max(ws_tx.max_row + 1, len(tx_list) + 2)):
            for c in range(1, 11):
                cell = ws_tx.cell(r, c)
                if type(cell).__name__ != "MergedCell":
                    cell.value = None

        # Clear existing Summary Sheet rows (skip MergedCells)
        for r in range(1, max(ws_summary.max_row + 1, 35)):
            for c in range(1, 12):
                cell = ws_summary.cell(r, c)
                if type(cell).__name__ != "MergedCell":
                    cell.value = None
    else:
        wb = openpyxl.Workbook()
        ws_summary = wb.active
        ws_summary.title = "Petty Cash Summary "
        ws_tx = wb.create_sheet(title="Petty Cash Sheet")

    ws_summary.views.sheetView[0].showGridLines = True
    ws_tx.views.sheetView[0].showGridLines = True

    # -------------------------------------------------------------
    # 1. Populate 'Petty Cash Sheet'
    # -------------------------------------------------------------
    tx_headers = [
        "Date", "Ledger", "Memo / Description", "Receipt", "Payment",
        "Oustanding Balance", "Approved", "Requested By", "Category", "Project"
    ]
    for c_idx, h_text in enumerate(tx_headers, start=1):
        cell = ws_tx.cell(1, c_idx, h_text)
        cell.font = FONT_HEADER
        cell.fill = YELLOW_FILL
        cell.border = ALL_THIN_BORDER
        cell.alignment = Alignment(horizontal="center" if c_idx in [1, 4, 5, 6, 7, 8] else "left", vertical="center")

    # Add Data Rows
    for r_idx, tx in enumerate(tx_list, start=2):
        parsed_dt = parse_date_for_excel(tx.get("date", ""))
        rec = tx.get("receipt") if tx.get("receipt") else None
        pay = tx.get("payment") if tx.get("payment") else None
        bal = tx.get("balance", 0.0)

        ws_tx.cell(r_idx, 1, parsed_dt)
        ws_tx.cell(r_idx, 2, tx.get("ledger", ""))
        ws_tx.cell(r_idx, 3, tx.get("memo", ""))
        ws_tx.cell(r_idx, 4, rec)
        ws_tx.cell(r_idx, 5, pay)
        ws_tx.cell(r_idx, 6, bal)
        ws_tx.cell(r_idx, 7, tx.get("approved", ""))
        ws_tx.cell(r_idx, 8, tx.get("requested_by", ""))
        ws_tx.cell(r_idx, 9, tx.get("category", ""))
        ws_tx.cell(r_idx, 10, tx.get("project", ""))

        for col_idx in range(1, 11):
            cell = ws_tx.cell(r_idx, col_idx)
            cell.font = FONT_REGULAR
            cell.border = ALL_THIN_BORDER
            if col_idx == 1:
                cell.alignment = Alignment(horizontal="center")
                cell.number_format = "yyyy-mm-dd"
            elif col_idx in [4, 5, 6]:
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = "#,##0.00"
            else:
                cell.alignment = Alignment(horizontal="left")

    # Set Column Widths for Petty Cash Sheet
    tx_col_widths = {
        "A": 12, "B": 20, "C": 50, "D": 14, "E": 14,
        "F": 18, "G": 16, "H": 16, "I": 24, "J": 30
    }
    for col_letter, width in tx_col_widths.items():
        ws_tx.column_dimensions[col_letter].width = width

    # -------------------------------------------------------------
    # 2. Populate 'Petty Cash Summary '
    # -------------------------------------------------------------
    # Left Pivot Table: Columns A to C
    ws_summary.cell(3, 1, "Row Labels").font = FONT_BOLD
    ws_summary.cell(3, 2, "Sum of Receipt").font = FONT_BOLD
    ws_summary.cell(3, 3, "Sum of Payment").font = FONT_BOLD

    for c in range(1, 4):
        ws_summary.cell(3, c).border = ALL_THIN_BORDER
        ws_summary.cell(3, c).alignment = Alignment(horizontal="left" if c == 1 else "right")

    pivot_rows = summary_data["pivot_rows"]
    curr_pivot_row = 4
    for prow in pivot_rows:
        ws_summary.cell(curr_pivot_row, 1, prow["project"]).font = FONT_REGULAR
        ws_summary.cell(curr_pivot_row, 1).border = ALL_THIN_BORDER

        c_rec = ws_summary.cell(curr_pivot_row, 2, prow["sum_receipt"])
        c_rec.font = FONT_REGULAR
        c_rec.border = ALL_THIN_BORDER
        c_rec.number_format = "#,##0.00"

        c_pay = ws_summary.cell(curr_pivot_row, 3, prow["sum_payment"])
        c_pay.font = FONT_REGULAR
        c_pay.border = ALL_THIN_BORDER
        c_pay.number_format = "#,##0.00"

        curr_pivot_row += 1

    # Pivot Grand Total
    ws_summary.cell(curr_pivot_row, 1, "Grand Total").font = FONT_BOLD
    ws_summary.cell(curr_pivot_row, 1).border = ALL_THIN_BORDER

    tot_rec_cell = ws_summary.cell(curr_pivot_row, 2, f"=SUM(B4:B{curr_pivot_row - 1})")
    tot_rec_cell.font = FONT_BOLD
    tot_rec_cell.border = ALL_THIN_BORDER
    tot_rec_cell.number_format = "#,##0.00"

    tot_pay_cell = ws_summary.cell(curr_pivot_row, 3, f"=SUM(C4:C{curr_pivot_row - 1})")
    tot_pay_cell.font = FONT_BOLD
    tot_pay_cell.border = ALL_THIN_BORDER
    tot_pay_cell.number_format = "#,##0.00"

    # If native pivot exists in template, update cache range and refresh flag
    if use_template and ws_summary._pivots:
        try:
            pivot = ws_summary._pivots[0]
            if pivot.cache and pivot.cache.cacheSource:
                pivot.cache.cacheSource.worksheetSource.ref = f"A1:J{len(tx_list) + 1}"
                pivot.cache.refreshOnLoad = True
            if pivot.location:
                pivot.location.ref = f"A3:C{curr_pivot_row}"
        except Exception as e:
            print("Warning updating native pivot metadata:", e)

    # Right Reconciliation Statement: Columns I to K
    # Row 2: Title Banner
    merged_ranges = [str(rng) for rng in ws_summary.merged_cells.ranges]
    if "I2:K2" not in merged_ranges:
        ws_summary.merge_cells("I2:K2")
    title_cell = ws_summary.cell(2, 9, "Petty Cash Summary")
    title_cell.font = FONT_TITLE_WHITE
    title_cell.fill = HEADER_BLUE_FILL
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    for c in range(9, 12):
        ws_summary.cell(2, c).border = ALL_THIN_BORDER

    # Row 3: Column Headers
    ws_summary.cell(3, 9, "Particulares").font = FONT_TITLE_WHITE
    ws_summary.cell(3, 9).fill = HEADER_BLUE_FILL
    ws_summary.cell(3, 9).border = ALL_THIN_BORDER

    ws_summary.cell(3, 10, "Amount").font = FONT_TITLE_WHITE
    ws_summary.cell(3, 10).fill = HEADER_BLUE_FILL
    ws_summary.cell(3, 10).border = ALL_THIN_BORDER

    ws_summary.cell(3, 11, "Amount").font = FONT_TITLE_WHITE
    ws_summary.cell(3, 11).fill = HEADER_BLUE_FILL
    ws_summary.cell(3, 11).border = ALL_THIN_BORDER

    # Row 4: Opening Balance
    ws_summary.cell(4, 9, "Petty Cash Opening Balance").font = FONT_REGULAR
    ws_summary.cell(4, 9).border = ALL_THIN_BORDER
    ws_summary.cell(4, 10, "").border = ALL_THIN_BORDER
    op_cell = ws_summary.cell(4, 11, opening_balance)
    op_cell.font = FONT_REGULAR
    op_cell.border = ALL_THIN_BORDER
    op_cell.number_format = "#,##0.00"

    # Row 5: Start Date
    ws_summary.cell(5, 9, f"({start_date})" if start_date else "").font = FONT_REGULAR
    ws_summary.cell(5, 9).border = ALL_THIN_BORDER
    ws_summary.cell(5, 10, "").border = ALL_THIN_BORDER
    ws_summary.cell(5, 11, "").border = ALL_THIN_BORDER

    # Row 6: Empty spacer row with borders
    for c in range(9, 12):
        ws_summary.cell(6, c).border = ALL_THIN_BORDER

    # Row 7: Additions Header
    ws_summary.cell(7, 9, "Additions").font = FONT_BOLD
    ws_summary.cell(7, 9).fill = YELLOW_FILL
    ws_summary.cell(7, 9).border = ALL_THIN_BORDER
    ws_summary.cell(7, 10, "").border = ALL_THIN_BORDER

    # Additions list
    additions = summary_data["additions"]
    add_start_row = 8
    curr_add_row = add_start_row

    for item in additions:
        ws_summary.cell(curr_add_row, 9, item["particular"]).font = FONT_REGULAR
        ws_summary.cell(curr_add_row, 9).border = ALL_THIN_BORDER

        amt_c = ws_summary.cell(curr_add_row, 10, item["amount"])
        amt_c.font = FONT_REGULAR
        amt_c.border = ALL_THIN_BORDER
        amt_c.number_format = "#,##0.00"

        ws_summary.cell(curr_add_row, 11, "").border = ALL_THIN_BORDER
        curr_add_row += 1

    add_end_row = curr_add_row - 1 if additions else 8
    add_sum_cell = ws_summary.cell(7, 11, f"=+SUM(J{add_start_row}:J{add_end_row})" if additions else 0)
    add_sum_cell.font = FONT_BOLD
    add_sum_cell.border = ALL_THIN_BORDER
    add_sum_cell.number_format = "#,##0.00"

    # Withdraw Header Row
    withdraw_hdr_row = curr_add_row
    ws_summary.cell(withdraw_hdr_row, 9, "Withdraw").font = FONT_BOLD
    ws_summary.cell(withdraw_hdr_row, 9).fill = YELLOW_FILL
    ws_summary.cell(withdraw_hdr_row, 9).border = ALL_THIN_BORDER
    ws_summary.cell(withdraw_hdr_row, 10, "").border = ALL_THIN_BORDER

    withdrawals = summary_data["withdrawals"]
    w_start_row = withdraw_hdr_row + 1
    curr_w_row = w_start_row

    for item in withdrawals:
        ws_summary.cell(curr_w_row, 9, item["particular"]).font = FONT_REGULAR
        ws_summary.cell(curr_w_row, 9).border = ALL_THIN_BORDER

        amt_c = ws_summary.cell(curr_w_row, 10, item["amount"])
        amt_c.font = FONT_REGULAR
        amt_c.border = ALL_THIN_BORDER
        amt_c.number_format = "#,##0.00"

        ws_summary.cell(curr_w_row, 11, "").border = ALL_THIN_BORDER
        curr_w_row += 1

    w_end_row = curr_w_row - 1 if withdrawals else w_start_row
    w_sum_cell = ws_summary.cell(withdraw_hdr_row, 11, f"=-SUM(J{w_start_row}:J{w_end_row})" if withdrawals else 0)
    w_sum_cell.font = FONT_BOLD
    w_sum_cell.border = ALL_THIN_BORDER
    w_sum_cell.number_format = "#,##0.00"

    # Spacer rows before closing balance
    spacer_row = curr_w_row
    for c in range(9, 12):
        ws_summary.cell(spacer_row, c).border = ALL_THIN_BORDER
    spacer_row2 = spacer_row + 1
    for c in range(9, 12):
        ws_summary.cell(spacer_row2, c).border = ALL_THIN_BORDER

    closing_row = spacer_row2 + 1
    closing_label = f"Closing balance as on {end_date}" if end_date else "Closing balance"
    ws_summary.cell(closing_row, 9, closing_label).font = FONT_BOLD
    ws_summary.cell(closing_row, 9).border = ALL_THIN_BORDER
    ws_summary.cell(closing_row, 10, "").border = ALL_THIN_BORDER

    closing_cell = ws_summary.cell(closing_row, 11, f"=+SUM(K4:K{closing_row - 1})")
    closing_cell.font = FONT_BOLD
    closing_cell.border = ALL_THIN_BORDER
    closing_cell.number_format = "#,##0.00"

    # Set Column Widths for Petty Cash Summary
    summary_col_widths = {
        "A": 32, "B": 16, "C": 16, "D": 5, "E": 5, "F": 5, "G": 5, "H": 5,
        "I": 40, "J": 16, "K": 18
    }
    for col_letter, width in summary_col_widths.items():
        ws_summary.column_dimensions[col_letter].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_drilldown_excel(project: str, tx_type: str, transactions: List[Dict[str, Any]]) -> io.BytesIO:
    """
    Generates a dedicated Excel sheet of the background transactions for a specific pivot value,
    including Date, Ledger, Memo, Receipt, Payment, Outstanding Balance, Approved,
    Requested By, Category, and Project.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Details - {project[:20]}"
    ws.views.sheetView[0].showGridLines = True

    # Title Banner
    ws.merge_cells("A1:J1")
    title = ws.cell(1, 1, f"Background Transactions: {project} ({tx_type.upper()})")
    title.font = FONT_TITLE_WHITE
    title.fill = HEADER_BLUE_FILL
    title.alignment = Alignment(horizontal="center", vertical="center")

    headers = [
        "Date", "Ledger", "Memo / Description", "Receipt", "Payment",
        "Oustanding Balance", "Approved", "Requested By", "Category", "Project"
    ]
    for c_idx, h_text in enumerate(headers, start=1):
        cell = ws.cell(2, c_idx, h_text)
        cell.font = FONT_HEADER
        cell.fill = YELLOW_FILL
        cell.border = ALL_THIN_BORDER
        cell.alignment = Alignment(horizontal="center" if c_idx in [1, 4, 5, 6, 7, 8] else "left")

    total_receipt = 0.0
    total_payment = 0.0

    for r_idx, tx in enumerate(transactions, start=3):
        parsed_dt = parse_date_for_excel(tx.get("date", ""))
        rec = tx.get("receipt") if tx.get("receipt") else None
        pay = tx.get("payment") if tx.get("payment") else None
        bal = tx.get("balance", 0.0)

        if rec:
            total_receipt += float(rec)
        if pay:
            total_payment += float(pay)

        ws.cell(r_idx, 1, parsed_dt)
        ws.cell(r_idx, 2, tx.get("ledger", ""))
        ws.cell(r_idx, 3, tx.get("memo", ""))
        ws.cell(r_idx, 4, rec)
        ws.cell(r_idx, 5, pay)
        ws.cell(r_idx, 6, bal)
        ws.cell(r_idx, 7, tx.get("approved", ""))
        ws.cell(r_idx, 8, tx.get("requested_by", ""))
        ws.cell(r_idx, 9, tx.get("category", ""))
        ws.cell(r_idx, 10, tx.get("project", ""))

        for c_idx in range(1, 11):
            c = ws.cell(r_idx, c_idx)
            c.font = FONT_REGULAR
            c.border = ALL_THIN_BORDER
            if c_idx == 1:
                c.alignment = Alignment(horizontal="center")
                c.number_format = "yyyy-mm-dd"
            elif c_idx in [4, 5, 6]:
                c.alignment = Alignment(horizontal="right")
                c.number_format = "#,##0.00"

    # Add Totals Row
    tot_row = len(transactions) + 3
    ws.cell(tot_row, 1, "Total").font = FONT_BOLD
    ws.cell(tot_row, 1).border = ALL_THIN_BORDER
    for c_idx in range(2, 4):
        ws.cell(tot_row, c_idx, "").border = ALL_THIN_BORDER

    tot_rec_c = ws.cell(tot_row, 4, total_receipt if total_receipt > 0 else "")
    tot_rec_c.font = FONT_BOLD
    tot_rec_c.border = ALL_THIN_BORDER
    tot_rec_c.number_format = "#,##0.00"

    tot_pay_c = ws.cell(tot_row, 5, total_payment if total_payment > 0 else "")
    tot_pay_c.font = FONT_BOLD
    tot_pay_c.border = ALL_THIN_BORDER
    tot_pay_c.number_format = "#,##0.00"

    for c_idx in range(6, 11):
        ws.cell(tot_row, c_idx, "").border = ALL_THIN_BORDER

    col_widths = {
        "A": 14, "B": 20, "C": 48, "D": 16, "E": 16,
        "F": 18, "G": 16, "H": 16, "J": 24, "K": 28
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
