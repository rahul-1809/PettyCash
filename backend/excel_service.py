import io
import os
import re
import datetime
import zipfile
import base64
import html
from typing import List, Dict, Any, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink
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

    header_indexes = {}
    for r in range(1, min(tx_sheet.max_row + 1, 10)):
        row_vals = [str(tx_sheet.cell(r, c).value or "").strip().lower() for c in range(1, tx_sheet.max_column + 1)]
        if any("date" in v for v in row_vals) and any("receipt" in v or "payment" in v for v in row_vals):
            header_row = r
            found_headers = True
            header_indexes = {value: index + 1 for index, value in enumerate(row_vals) if value}
            break

    start_data_row = header_row + 1 if found_headers else 2

    for r in range(start_data_row, tx_sheet.max_row + 1):
        def cell_value(*names, default=None):
            index = next((header_indexes[name] for name in names if name in header_indexes), None)
            return tx_sheet.cell(r, index).value if index else default

        d_val = cell_value("date", default=tx_sheet.cell(r, 1).value)
        ledger = cell_value("ledger", default=tx_sheet.cell(r, 2).value)
        memo = cell_value("memo / description", "memo", default=tx_sheet.cell(r, 3).value)
        receipt = parse_float(cell_value("receipt", default=tx_sheet.cell(r, 4).value))
        payment = parse_float(cell_value("payment", default=tx_sheet.cell(r, 5).value))
        balance = parse_float(cell_value("ouststanding balance", "outstanding balance", default=tx_sheet.cell(r, 6).value))
        approved = cell_value("approved", default=tx_sheet.cell(r, 7).value)
        requested_by = cell_value("requested by", default=tx_sheet.cell(r, 8).value)
        category = cell_value("category", default=tx_sheet.cell(r, 9).value)
        project = cell_value("project", default=tx_sheet.cell(r, 10).value)
        status = cell_value("status", default="NA") or "NA"
        notes = cell_value("notes", default="")

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
            "status": str(status).strip() if str(status).strip() in {"Paid", "Unpaid", "Progress", "NA"} else "NA",
            "supportings": [],
            "notes": str(notes or "").strip(),
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
            for c in range(1, 14):
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
        "Oustanding Balance", "Approved", "Requested By", "Category", "Project",
        "Status", "Supportings", "Notes"
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
        ws_tx.cell(r_idx, 11, tx.get("status", "NA"))
        ws_tx.cell(r_idx, 12, ", ".join(item.get("name", "") for item in tx.get("supportings", [])))
        ws_tx.cell(r_idx, 13, tx.get("notes", ""))

        for col_idx in range(1, 14):
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
        "F": 18, "G": 16, "H": 16, "I": 24, "J": 30,
        "K": 14, "L": 30, "M": 40
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
            tx for tx in tx_list
            if (project == "Grand Total" or (tx.get("project", "").strip() or "Unassigned") == project)
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
            "Oustanding Balance", "Approved", "Requested By", "Category", "Project"
        ]
        for col_idx, header in enumerate(headers, start=1):
            header_cell = sheet.cell(2, col_idx, header)
            header_cell.font = FONT_HEADER
            header_cell.fill = YELLOW_FILL
            header_cell.border = ALL_THIN_BORDER

        for row_idx, tx in enumerate(rows, start=3):
            values = [
                parse_date_for_excel(tx.get("date", "")),
                tx.get("ledger", ""),
                tx.get("memo", ""),
                tx.get("receipt") or None,
                tx.get("payment") or None,
                tx.get("balance", 0.0),
                tx.get("approved", ""),
                tx.get("requested_by", ""),
                tx.get("category", ""),
                tx.get("project", ""),
            ]
            for col_idx, value in enumerate(values, start=1):
                detail_cell = sheet.cell(row_idx, col_idx, value)
                detail_cell.font = FONT_REGULAR
                detail_cell.border = ALL_THIN_BORDER
                if col_idx == 1:
                    detail_cell.number_format = "yyyy-mm-dd"
                elif col_idx in [4, 5, 6]:
                    detail_cell.number_format = "#,##0.00"

        total_row = len(rows) + 3
        sheet.cell(total_row, 1, "Total").font = FONT_BOLD
        sheet.cell(total_row, 1).border = ALL_THIN_BORDER
        for col_idx in range(2, 4):
            sheet.cell(total_row, col_idx).border = ALL_THIN_BORDER
        for col_idx, field in ((4, "receipt"), (5, "payment")):
            total_cell = sheet.cell(
                total_row,
                col_idx,
                sum(float(tx.get(field, 0) or 0) for tx in rows) or "",
            )
            total_cell.font = FONT_BOLD
            total_cell.border = ALL_THIN_BORDER
            total_cell.number_format = "#,##0.00"
        for col_idx in range(6, 11):
            sheet.cell(total_row, col_idx).border = ALL_THIN_BORDER

        for col_letter, width in {
            "A": 14, "B": 20, "C": 48, "D": 16, "E": 16,
            "F": 18, "G": 16, "H": 16, "I": 24, "J": 28,
        }.items():
            sheet.column_dimensions[col_letter].width = width

        drilldown_sheets[key] = sheet
        return sheet

    for prow in pivot_rows:
        project = prow["project"]
        if prow["sum_receipt"]:
            create_drilldown_sheet(project, "receipt")
        if prow["sum_payment"]:
            create_drilldown_sheet(project, "payment")
    create_drilldown_sheet("Grand Total", "receipt")
    create_drilldown_sheet("Grand Total", "payment")

    for prow in pivot_rows:
        ws_summary.cell(curr_pivot_row, 1, prow["project"]).font = FONT_REGULAR
        ws_summary.cell(curr_pivot_row, 1).border = ALL_THIN_BORDER

        c_rec = ws_summary.cell(curr_pivot_row, 2, prow["sum_receipt"])
        c_rec.font = FONT_REGULAR
        c_rec.border = ALL_THIN_BORDER
        c_rec.number_format = "#,##0.00"
        if prow["sum_receipt"]:
            add_drilldown_link(c_rec, prow["project"], "receipt")

        c_pay = ws_summary.cell(curr_pivot_row, 3, prow["sum_payment"])
        c_pay.font = FONT_REGULAR
        c_pay.border = ALL_THIN_BORDER
        c_pay.number_format = "#,##0.00"
        if prow["sum_payment"]:
            add_drilldown_link(c_pay, prow["project"], "payment")

        curr_pivot_row += 1

    # Pivot Grand Total
    ws_summary.cell(curr_pivot_row, 1, "Grand Total").font = FONT_BOLD
    ws_summary.cell(curr_pivot_row, 1).border = ALL_THIN_BORDER

    tot_rec_cell = ws_summary.cell(curr_pivot_row, 2, f"=SUM(B4:B{curr_pivot_row - 1})")
    tot_rec_cell.font = FONT_BOLD
    tot_rec_cell.border = ALL_THIN_BORDER
    tot_rec_cell.number_format = "#,##0.00"
    add_drilldown_link(tot_rec_cell, "Grand Total", "receipt")

    tot_pay_cell = ws_summary.cell(curr_pivot_row, 3, f"=SUM(C4:C{curr_pivot_row - 1})")
    tot_pay_cell.font = FONT_BOLD
    tot_pay_cell.border = ALL_THIN_BORDER
    tot_pay_cell.number_format = "#,##0.00"
    add_drilldown_link(tot_pay_cell, "Grand Total", "payment")

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
        add_drilldown_link(amt_c, item["project"], "receipt")

        ws_summary.cell(curr_add_row, 11, "").border = ALL_THIN_BORDER
        curr_add_row += 1

    add_end_row = curr_add_row - 1 if additions else 8
    add_sum_cell = ws_summary.cell(7, 11, f"=+SUM(J{add_start_row}:J{add_end_row})" if additions else 0)
    add_sum_cell.font = FONT_BOLD
    add_sum_cell.border = ALL_THIN_BORDER
    add_sum_cell.number_format = "#,##0.00"
    add_drilldown_link(add_sum_cell, "Grand Total", "receipt")

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
        add_drilldown_link(amt_c, item["project"], "payment")

        ws_summary.cell(curr_w_row, 11, "").border = ALL_THIN_BORDER
        curr_w_row += 1

    w_end_row = curr_w_row - 1 if withdrawals else w_start_row
    w_sum_cell = ws_summary.cell(withdraw_hdr_row, 11, f"=-SUM(J{w_start_row}:J{w_end_row})" if withdrawals else 0)
    w_sum_cell.font = FONT_BOLD
    w_sum_cell.border = ALL_THIN_BORDER
    w_sum_cell.number_format = "#,##0.00"
    add_drilldown_link(w_sum_cell, "Grand Total", "payment")

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


# ─── Session ZIP Bundle & Offline Evidence Viewer ────────────────────────────

def _generate_session_evidence_html(
    session_name: str,
    opening_balance: float,
    start_date: str,
    end_date: str,
    transactions: List[Dict[str, Any]],
    summary: Dict[str, Any],
    tx_supportings_map: Dict[str, List[Dict[str, str]]],
) -> str:
    """Generate modern, offline self-contained HTML evidence viewer with live search."""
    tot_receipts = summary.get("total_receipts", 0.0)
    tot_payments = summary.get("total_payments", 0.0)
    closing_balance = summary.get("closing_balance", opening_balance + tot_receipts - tot_payments)
    
    op_str = f"₹{opening_balance:,.2f}"
    rec_str = f"₹{tot_receipts:,.2f}"
    pay_str = f"₹{tot_payments:,.2f}"
    cl_str = f"₹{closing_balance:,.2f}"
    
    rows_html = []
    for idx, tx in enumerate(transactions):
        tx_id = tx.get("id") or f"row_{idx+1}"
        supp_list = tx_supportings_map.get(tx_id, [])
        
        supp_badges = []
        for s in supp_list:
            s_name = html.escape(s.get("name", "Document"))
            s_path = html.escape(s.get("rel_path", "#"))
            supp_badges.append(
                f'<a class="doc-badge" href="{s_path}" target="_blank" title="{s_name}">📄 {s_name}</a>'
            )
        supp_html = " ".join(supp_badges) if supp_badges else '<span class="muted">—</span>'

        date_val = html.escape(str(tx.get("date") or ""))
        ledger_val = html.escape(str(tx.get("ledger") or ""))
        memo_val = html.escape(str(tx.get("memo") or ""))
        project_val = html.escape(str(tx.get("project") or ""))
        category_val = html.escape(str(tx.get("category") or ""))
        status_val = html.escape(str(tx.get("status") or "NA"))
        
        r_num = float(tx.get("receipt") or 0.0)
        p_num = float(tx.get("payment") or 0.0)
        b_num = float(tx.get("balance") or 0.0)
        
        r_disp = f"+₹{r_num:,.2f}" if r_num > 0 else "—"
        p_disp = f"-₹{p_num:,.2f}" if p_num > 0 else "—"
        b_disp = f"₹{b_num:,.2f}"
        b_cls = "neg" if b_num < 0 else "pos"
        
        rows_html.append(f"""
        <tr class="tx-row" data-search="{date_val.lower()} {ledger_val.lower()} {memo_val.lower()} {project_val.lower()} {category_val.lower()}">
            <td class="mono">{date_val}</td>
            <td>{ledger_val}</td>
            <td class="desc"><strong>{memo_val}</strong></td>
            <td><span class="badge project">{project_val}</span></td>
            <td><span class="muted">{category_val}</span></td>
            <td class="mono num rec">{r_disp}</td>
            <td class="mono num pay">{p_disp}</td>
            <td class="mono num {b_cls}"><strong>{b_disp}</strong></td>
            <td><span class="badge status">{status_val}</span></td>
            <td>{supp_html}</td>
        </tr>""")

    tbody_content = "\n".join(rows_html) if rows_html else '<tr><td colspan="10" class="empty">No transactions found.</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(session_name)} - Offline Evidence Viewer</title>
<style>
:root {{
  --bg: #090d16;
  --surface: #111827;
  --surface-border: #1f2937;
  --text: #f3f4f6;
  --text-muted: #9ca3af;
  --primary: #10b981;
  --primary-bg: rgba(16, 185, 129, 0.1);
  --danger: #f43f5e;
  --danger-bg: rgba(244, 63, 94, 0.1);
  --warning: #f59e0b;
  --warning-bg: rgba(245, 158, 11, 0.1);
  --mono-font: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  padding: 24px;
}}
.container {{
  max-width: 1400px;
  margin: 0 auto;
}}
header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--surface-border);
  margin-bottom: 24px;
}}
.title-group h1 {{
  font-size: 20px;
  font-weight: 700;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.title-group p {{
  color: var(--text-muted);
  font-size: 13px;
  margin-top: 4px;
}}
.header-badge {{
  font-size: 11px;
  font-weight: 600;
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
  padding: 4px 10px;
  border-radius: 9999px;
}}
.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.kpi-card {{
  background: var(--surface);
  border: 1px solid var(--surface-border);
  border-radius: 10px;
  padding: 16px;
}}
.kpi-label {{
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.05em;
}}
.kpi-value {{
  font-size: 22px;
  font-weight: 700;
  font-family: var(--mono-font);
  margin-top: 6px;
}}
.kpi-value.green {{ color: #34d399; }}
.kpi-value.amber {{ color: #fbbf24; }}
.kpi-value.rose {{ color: #f87171; }}
.toolbar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}}
.search-box {{
  background: var(--surface);
  border: 1px solid var(--surface-border);
  color: var(--text);
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  width: 100%;
  max-width: 360px;
  outline: none;
}}
.search-box:focus {{
  border-color: var(--primary);
}}
.table-card {{
  background: var(--surface);
  border: 1px solid var(--surface-border);
  border-radius: 10px;
  overflow: hidden;
}}
.table-wrap {{
  overflow-x: auto;
  max-height: 700px;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 12px;
}}
th {{
  background: #0d131f;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  padding: 12px 14px;
  border-bottom: 1px solid var(--surface-border);
  letter-spacing: 0.05em;
  position: sticky;
  top: 0;
  z-index: 10;
}}
td {{
  padding: 10px 14px;
  border-bottom: 1px solid #1a2234;
  vertical-align: middle;
}}
tr:hover td {{
  background: rgba(255, 255, 255, 0.02);
}}
.mono {{
  font-family: var(--mono-font);
}}
.num {{
  text-align: right;
}}
.rec {{
  color: #34d399;
}}
.pay {{
  color: #fbbf24;
}}
.neg {{
  color: #f87171;
}}
.pos {{
  color: #f3f4f6;
}}
.desc {{
  max-width: 320px;
  word-break: break-word;
}}
.badge {{
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}}
.badge.project {{
  background: #1e293b;
  color: #cbd5e1;
}}
.badge.status {{
  background: #1e293b;
  color: #94a3b8;
}}
.doc-badge {{
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  background: rgba(16, 185, 129, 0.12);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
  padding: 2px 8px;
  border-radius: 4px;
  text-decoration: none;
  margin: 2px 0;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.doc-badge:hover {{
  background: rgba(16, 185, 129, 0.25);
}}
.muted {{
  color: #64748b;
}}
.empty {{
  text-align: center;
  padding: 40px;
  color: var(--text-muted);
}}
footer {{
  margin-top: 24px;
  text-align: center;
  font-size: 11px;
  color: #64748b;
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="title-group">
      <h1>📊 {html.escape(session_name)}</h1>
      <p>Period: <b>{html.escape(start_date or 'N/A')}</b> to <b>{html.escape(end_date or 'N/A')}</b> &bull; Total Entries: <b>{len(transactions)}</b></p>
    </div>
    <div class="header-badge">PETTY CASH AUDIT BUNDLE</div>
  </header>

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">Opening Balance</div>
      <div class="kpi-value {'rose' if opening_balance < 0 else ''}">{op_str}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Total Receipts</div>
      <div class="kpi-value green">{rec_str}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Total Payments</div>
      <div class="kpi-value amber">{pay_str}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Closing Balance</div>
      <div class="kpi-value {'rose' if closing_balance < 0 else 'green'}">{cl_str}</div>
    </div>
  </div>

  <div class="toolbar">
    <input type="text" id="searchInput" class="search-box" placeholder="Filter by date, description, project, ledger..." onkeyup="filterRows()">
    <span id="matchCount" style="font-size: 12px; color: var(--text-muted);">Showing {len(transactions)} transactions</span>
  </div>

  <div class="table-card">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Ledger</th>
            <th>Description / Memo</th>
            <th>Project</th>
            <th>Category</th>
            <th style="text-align: right;">Receipt</th>
            <th style="text-align: right;">Payment</th>
            <th style="text-align: right;">Balance</th>
            <th>Status</th>
            <th>Evidence Files</th>
          </tr>
        </thead>
        <tbody id="txBody">
          {tbody_content}
        </tbody>
      </table>
    </div>
  </div>

  <footer>
    Generated by PettyCash Pro Enterprise System &bull; Offline Audit Evidence Package &bull; All supporting files are hyperlinked relatively within this package.
  </footer>
</div>

<script>
function filterRows() {{
  const query = document.getElementById('searchInput').value.toLowerCase().trim();
  const rows = document.querySelectorAll('.tx-row');
  let matchCount = 0;
  rows.forEach(row => {{
    const text = row.getAttribute('data-search') || '';
    if (!query || text.includes(query)) {{
      row.style.display = '';
      matchCount++;
    }} else {{
      row.style.display = 'none';
    }}
  }});
  document.getElementById('matchCount').innerText = 'Showing ' + matchCount + ' of ' + rows.length + ' transactions';
}}
</script>
</body>
</html>"""


def generate_session_zip_bundle(
    opening_balance: float,
    start_date: str,
    end_date: str,
    transactions: List[Dict[str, Any]],
    session_name: Optional[str] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> io.BytesIO:
    """Generate complete session ZIP package containing the styled Excel workbook,
    interactive offline HTML evidence viewer, and all attached voucher documents.

    Structure of ZIP:
    ├── {session_name}.xlsx
    ├── evidence_viewer.html
    └── supportings/
        ├── tx1_bill.pdf
        └── tx2_receipt.png
    """
    if not summary:
        summary = recalculate_summary(opening_balance, start_date, end_date, transactions)

    zip_buffer = io.BytesIO()
    display_name = session_name or f"Petty Cash {start_date} to {end_date}"
    clean_session_name = re.sub(r"[^A-Za-z0-9._-]", "_", display_name).strip("_")
    if not clean_session_name:
        clean_session_name = "Petty_Cash_Session"

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        tx_supportings_map = {}
        used_filenames = set()

        # 1. Process and bundle supportings
        for idx, tx in enumerate(transactions):
            tx_id = tx.get("id") or f"row_{idx+1}"
            tx_supportings_map[tx_id] = []
            raw_supportings = tx.get("supportings") or []
            if isinstance(raw_supportings, dict):
                raw_supportings = [raw_supportings]

            for s_idx, supp in enumerate(raw_supportings):
                if not isinstance(supp, dict):
                    continue
                orig_name = supp.get("name") or supp.get("original_filename") or f"supporting_{idx+1}_{s_idx+1}.bin"
                safe_orig = re.sub(r"[^A-Za-z0-9._-]", "_", orig_name)
                archive_filename = f"supportings/tx{idx+1}_{safe_orig}"

                counter = 1
                while archive_filename in used_filenames:
                    archive_filename = f"supportings/tx{idx+1}_{counter}_{safe_orig}"
                    counter += 1
                used_filenames.add(archive_filename)

                file_bytes = None
                raw_data = supp.get("data") or supp.get("file_data")
                if raw_data:
                    try:
                        file_bytes = base64.b64decode(raw_data)
                    except Exception:
                        file_bytes = None

                if not file_bytes and supp.get("id"):
                    try:
                        from backend import database
                        with database.get_connection() as conn:
                            marker = database._placeholder()
                            f_row = conn.execute(
                                f"SELECT file_data FROM supporting_files WHERE id={marker}",
                                (supp["id"],),
                            ).fetchone()
                            if f_row and f_row.get("file_data"):
                                file_bytes = base64.b64decode(f_row["file_data"])
                    except Exception:
                        file_bytes = None

                if file_bytes:
                    archive.writestr(archive_filename, file_bytes)
                    tx_supportings_map[tx_id].append({
                        "name": orig_name,
                        "rel_path": archive_filename,
                    })

        # 2. Add styled Excel workbook
        excel_stream = generate_styled_excel(opening_balance, start_date, end_date, transactions)
        archive.writestr(f"{clean_session_name}.xlsx", excel_stream.getvalue())

        # 3. Add offline Evidence Viewer HTML
        html_viewer = _generate_session_evidence_html(
            session_name=display_name,
            opening_balance=opening_balance,
            start_date=start_date,
            end_date=end_date,
            transactions=transactions,
            summary=summary,
            tx_supportings_map=tx_supportings_map,
        )
        archive.writestr("evidence_viewer.html", html_viewer.encode("utf-8"))

    zip_buffer.seek(0)
    return zip_buffer

