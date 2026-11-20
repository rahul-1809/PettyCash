import io
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

import openpyxl
from fastapi.testclient import TestClient

from backend import database
from backend.domain_repository import create_master_record
from backend.main import app
from backend.auth_service import create_session as create_auth_session
from backend.posting_service import post_request
from backend.receipt_service import create_company_receipt
from backend.report_service import (
    REQUIRED_12_COLUMNS,
    generate_legacy_12col_excel,
    generate_monthly_excel,
    generate_monthly_zip_bundle,
    get_monthly_report_data,
    parse_month_bounds,
)
from backend.request_service import (
    create_draft,
    manager_decision,
    submit_request,
)
from backend.supporting_service import upload_supporting_file
from backend.user_service import (
    create_assignment,
    create_bootstrap_admin,
    provision_user,
    review_assignment,
)
from backend.legacy_ledger_service import create_legacy_session


class Phase8Tests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "phase8.sqlite")
        database.DATABASE_URL = None
        database.init_db()

        self.admin = create_bootstrap_admin("admin", "admin@example.com", "a-secure-password")
        self.manager, _ = provision_user("manager", "manager@example.com", "Manager", self.admin["id"])
        self.employee, _ = provision_user("employee", "employee@example.com", "Employee", self.admin["id"])

        assignment = create_assignment(self.manager["id"], self.employee["id"], self.admin["id"])
        review_assignment(assignment["id"], self.manager["id"], "APPROVED")

        self.project_a = create_master_record("projects", "Project Alpha")
        self.project_b = create_master_record("projects", "Project Beta")
        self.ledger_office = create_master_record("ledgers", "Office Operations")
        self.ledger_travel = create_master_record("ledgers", "Travel Expenses")

        # Set initial cash balance
        marker = database._placeholder()
        with database.get_connection() as connection:
            connection.execute(
                f"""
                UPDATE cash_account_balances
                SET current_balance={marker}
                WHERE cash_account_id='system-main-cash'
                """,
                ("5000.00",),
            )
            connection.commit()

        self.admin_token = create_auth_session(self.admin["id"])
        self.employee_token = create_auth_session(self.employee["id"])
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        self.employee_headers = {"Authorization": f"Bearer {self.employee_token}"}
        self.client = TestClient(app)

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        self.temp_dir.cleanup()

    def _post_employee_request(
        self,
        amount="300.00",
        req_date="2026-11-05",
        post_date="2026-11-06",
        project_id=None,
        ledger_id=None,
        category="Stationery",
        purpose="Paper and pens",
        file_content=b"%PDF-1.7 receipt sample",
        filename="bill.pdf",
    ):
        proj = project_id or self.project_a["id"]
        ledg = ledger_id or self.ledger_office["id"]
        req = create_draft(
            self.employee["id"],
            proj,
            ledg,
            category,
            req_date,
            amount,
            purpose,
            "Notes on bill",
            self.manager["id"],
        )
        submit_request(req["id"], self.employee["id"])
        manager_decision(req["id"], self.manager["id"], "APPROVED", None)
        upload_supporting_file(
            req["id"],
            self.employee["id"],
            filename,
            "application/pdf",
            file_content,
        )
        post_request(req["id"], self.admin["id"], post_date)
        return req["id"]

    # ── Acceptance Criterion 1 & 2: Authoritative Totals & Exclusion of Unposted ──

    def test_monthly_report_matches_ledger_and_excludes_unposted(self):
        # 1. Post two requests in November 2026: 300.00 and 200.00
        self._post_employee_request(amount="300.00", req_date="2026-11-05", post_date="2026-11-06")
        self._post_employee_request(amount="200.00", req_date="2026-11-10", post_date="2026-11-12")

        # 2. Add one company receipt in November: 1000.00
        create_company_receipt(
            self.admin["id"],
            1000.00,
            "2026-11-01",
            "Petty cash monthly top-up",
            self.ledger_office["id"],
            "Cash replenishment",
            self.project_a["id"],
        )

        # 3. Create unposted requests in November:
        # A draft
        draft_req = create_draft(
            self.employee["id"],
            self.project_a["id"],
            self.ledger_office["id"],
            "Refreshments",
            "2026-11-15",
            "150.00",
            "Tea and coffee",
            None,
            self.manager["id"],
        )
        # A submitted pending approval
        sub_req = create_draft(
            self.employee["id"],
            self.project_b["id"],
            self.ledger_travel["id"],
            "Travel",
            "2026-11-20",
            "450.00",
            "Flight ticket",
            None,
            self.manager["id"],
        )
        submit_request(sub_req["id"], self.employee["id"])
        # A rejected request
        rej_req = create_draft(
            self.employee["id"],
            self.project_b["id"],
            self.ledger_travel["id"],
            "Travel",
            "2026-11-22",
            "999.00",
            "Luxury taxi",
            None,
            self.manager["id"],
        )
        submit_request(rej_req["id"], self.employee["id"])
        manager_decision(rej_req["id"], self.manager["id"], "REJECTED", "Too expensive")

        # Fetch monthly report for 2026-11
        data = get_monthly_report_data("2026-11")

        # Authoritative posted totals verification
        self.assertEqual(data["total_receipts"], 1000.00)
        self.assertEqual(data["total_payments"], 500.00)  # 300 + 200
        self.assertEqual(data["net_movement"], 500.00)    # 1000 - 500
        # Opening balance was 5000.00 -> Closing balance is 5500.00
        self.assertEqual(data["opening_balance"], 5000.00)
        self.assertEqual(data["closing_balance"], 5500.00)
        self.assertEqual(data["posted_count"], 3)

        # CRUCIAL: Verify unposted requests are listed separately and NOT in totals
        unposted = data["unposted_requests"]
        unposted_ids = [u["id"] for u in unposted]
        self.assertIn(draft_req["id"], unposted_ids)
        self.assertIn(sub_req["id"], unposted_ids)
        # Total payments in report must remain exactly 500.00, NOT 500 + 150 + 450
        self.assertEqual(data["total_payments"], 500.00)

        # Pending approvals & rejected counts
        self.assertEqual(data["pending_approvals_count"], 1)
        self.assertEqual(data["pending_approvals_total"], 450.00)
        self.assertEqual(data["rejected_count"], 1)
        self.assertEqual(data["rejected_total"], 999.00)

    # ── Acceptance Criterion 3: Unposted Requests Filtered by Request Date ──

    def test_unposted_requests_filtered_by_request_date(self):
        # Request with November date
        nov_req = create_draft(
            self.employee["id"],
            self.project_a["id"],
            self.ledger_office["id"],
            "Supplies",
            "2026-11-05",
            "50.00",
            "Pens",
            None,
            self.manager["id"],
        )
        # Request with December date
        dec_req = create_draft(
            self.employee["id"],
            self.project_a["id"],
            self.ledger_office["id"],
            "Supplies",
            "2026-12-05",
            "75.00",
            "Notebooks",
            None,
            self.manager["id"],
        )

        nov_data = get_monthly_report_data("2026-11")
        dec_data = get_monthly_report_data("2026-12")

        nov_unposted_ids = [u["id"] for u in nov_data["unposted_requests"]]
        dec_unposted_ids = [u["id"] for u in dec_data["unposted_requests"]]

        self.assertIn(nov_req["id"], nov_unposted_ids)
        self.assertNotIn(dec_req["id"], nov_unposted_ids)

        self.assertIn(dec_req["id"], dec_unposted_ids)
        self.assertNotIn(nov_req["id"], dec_unposted_ids)

    # ── Acceptance Criterion 4: Reconciliations of Breakdowns to Totals ──

    def test_breakdowns_reconcile_to_period_totals(self):
        self._post_employee_request(
            amount="300.00",
            req_date="2026-11-02",
            post_date="2026-11-03",
            project_id=self.project_a["id"],
            ledger_id=self.ledger_office["id"],
            category="Office Supplies",
        )
        self._post_employee_request(
            amount="450.00",
            req_date="2026-11-10",
            post_date="2026-11-12",
            project_id=self.project_b["id"],
            ledger_id=self.ledger_travel["id"],
            category="Local Travel",
        )
        self._post_employee_request(
            amount="250.00",
            req_date="2026-11-15",
            post_date="2026-11-15",
            project_id=self.project_a["id"],
            ledger_id=self.ledger_office["id"],
            category="Office Supplies",
        )
        create_company_receipt(
            self.admin["id"],
            1500.00,
            "2026-11-01",
            "Replenishment",
            self.ledger_office["id"],
            "Replenishment",
            self.project_a["id"],
        )

        data = get_monthly_report_data("2026-11")

        # Total payments: 300 + 450 + 250 = 1000.00
        # Total receipts: 1500.00
        self.assertEqual(data["total_payments"], 1000.00)
        self.assertEqual(data["total_receipts"], 1500.00)

        # 1. Daily movement sum must reconcile to total receipts and total payments
        daily_payments_sum = sum(d["payments"] for d in data["daily_movement"])
        daily_receipts_sum = sum(d["receipts"] for d in data["daily_movement"])
        self.assertEqual(round(daily_payments_sum, 2), 1000.00)
        self.assertEqual(round(daily_receipts_sum, 2), 1500.00)

        # 2. Spending by ledger must reconcile to total payments
        ledger_sum = sum(l["amount"] for l in data["spending_by_ledger"])
        self.assertEqual(round(ledger_sum, 2), 1000.00)

        # 3. Spending by category must reconcile to total payments
        category_sum = sum(c["amount"] for c in data["spending_by_category"])
        self.assertEqual(round(category_sum, 2), 1000.00)

        # 4. Spending by project must reconcile to total payments
        project_sum = sum(p["amount"] for p in data["spending_by_project"])
        self.assertEqual(round(project_sum, 2), 1000.00)

    # ── Acceptance Criterion 5: Required 12-Column Schema ──

    def test_exported_sheets_contain_exact_12_columns(self):
        self._post_employee_request(amount="120.00", post_date="2026-11-05")
        report_data = get_monthly_report_data("2026-11")

        # 1. Test Active Monthly Excel Export
        excel_buf = generate_monthly_excel(report_data)
        wb = openpyxl.load_workbook(excel_buf)

        self.assertIn("Petty Cash Sheet", wb.sheetnames)
        self.assertIn("Petty Cash Summary", wb.sheetnames)
        self.assertIn("Supporting Files", wb.sheetnames)

        tx_sheet = wb["Petty Cash Sheet"]
        actual_headers = [tx_sheet.cell(1, col).value for col in range(1, 13)]
        self.assertEqual(actual_headers, REQUIRED_12_COLUMNS)
        self.assertEqual(len(actual_headers), 12)
        # Ensure column 13 is empty
        self.assertIsNone(tx_sheet.cell(1, 13).value)

        # 2. Test Legacy Ledger 12-Column Export
        legacy_session = create_legacy_session(
            admin_id=self.admin["id"],
            name="Archived Session 2025",
            opening_balance=2500.0,
            start_date="2025-05-01",
            end_date="2025-05-31",
            transactions=[
                {
                    "date": "2025-05-10",
                    "ledger": "Courier",
                    "memo": "Postal stamps",
                    "payment": 80.0,
                    "receipt": 0.0,
                    "project": "Marketing",
                }
            ],
        )
        legacy_buf = generate_legacy_12col_excel(legacy_session)
        legacy_wb = openpyxl.load_workbook(legacy_buf)
        self.assertIn("Petty Cash Sheet", legacy_wb.sheetnames)
        legacy_headers = [legacy_wb["Petty Cash Sheet"].cell(1, col).value for col in range(1, 13)]
        self.assertEqual(legacy_headers, REQUIRED_12_COLUMNS)
        self.assertEqual(len(legacy_headers), 12)

    # ── Acceptance Criterion 6 & 7: ZIP Bundle & Relative Hyperlinks ──

    def test_zip_bundle_structure_and_relative_hyperlinks(self):
        req_id = self._post_employee_request(
            amount="350.00",
            post_date="2026-11-08",
            filename="receipt_taxi.pdf",
            file_content=b"%PDF-1.7 sample invoice content",
        )

        zip_buf = generate_monthly_zip_bundle("2026-11")
        with zipfile.ZipFile(zip_buf, mode="r") as archive:
            namelist = archive.namelist()

            # Verify presence of Excel file
            excel_files = [n for n in namelist if n.endswith(".xlsx")]
            self.assertEqual(len(excel_files), 1)
            excel_name = excel_files[0]

            # Verify presence of supporting file in supportings/
            supporting_entries = [n for n in namelist if n.startswith("supportings/")]
            self.assertGreaterEqual(len(supporting_entries), 1)
            target_sup = supporting_entries[0]
            self.assertTrue(target_sup.endswith("receipt_taxi.pdf"))

            # Open the workbook directly from the ZIP
            wb_data = archive.read(excel_name)
            wb = openpyxl.load_workbook(io.BytesIO(wb_data))

            # Verify relative hyperlink in Petty Cash Sheet (Column 11: Supportings)
            ws_tx = wb["Petty Cash Sheet"]
            sup_cell = ws_tx.cell(2, 11)
            self.assertIsNotNone(sup_cell.hyperlink)
            self.assertTrue(sup_cell.hyperlink.target.startswith("supportings/"))
            self.assertIn("receipt_taxi.pdf", sup_cell.hyperlink.target)

            # Verify relative hyperlink in Supporting Files sheet
            ws_sup = wb["Supporting Files"]
            link_cell = ws_sup.cell(2, 6)
            self.assertIsNotNone(link_cell.hyperlink)
            self.assertTrue(link_cell.hyperlink.target.startswith("supportings/"))

    # ── Acceptance Criterion 8: Read-Only (Does Not Mutate Financial Data) ──

    def test_export_generation_does_not_mutate_financial_data(self):
        self._post_employee_request(amount="100.00", post_date="2026-11-01")

        with database.get_connection() as conn:
            bal_before = conn.execute(
                "SELECT current_balance, version FROM cash_account_balances WHERE cash_account_id='system-main-cash'"
            ).fetchone()
            entries_count_before = conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]

        # Generate report and exports
        _ = get_monthly_report_data("2026-11")
        _ = generate_monthly_zip_bundle("2026-11")

        with database.get_connection() as conn:
            bal_after = conn.execute(
                "SELECT current_balance, version FROM cash_account_balances WHERE cash_account_id='system-main-cash'"
            ).fetchone()
            entries_count_after = conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]

        self.assertEqual(bal_before["current_balance"], bal_after["current_balance"])
        self.assertEqual(bal_before["version"], bal_after["version"])
        self.assertEqual(entries_count_before, entries_count_after)

    # ── Acceptance Criterion 9 & 10: API Integration, Validation & RBAC ──

    def test_api_monthly_report_and_export_endpoints(self):
        # 1. GET /api/reports/monthly
        res = self.client.get("/api/reports/monthly?month=2026-11", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["month"], "2026-11")

        # Invalid month format returns 400
        res_invalid = self.client.get("/api/reports/monthly?month=invalid", headers=self.admin_headers)
        self.assertEqual(res_invalid.status_code, 400)

        # 2. GET /api/reports/monthly/excel
        res_excel = self.client.get("/api/reports/monthly/excel?month=2026-11", headers=self.admin_headers)
        self.assertEqual(res_excel.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", res_excel.headers["content-type"])

        # 3. GET /api/reports/monthly/zip
        # Non-admin gets 403
        res_zip_emp = self.client.get("/api/reports/monthly/zip?month=2026-11", headers=self.employee_headers)
        self.assertEqual(res_zip_emp.status_code, 403)

        # Admin gets 200 and zip file
        res_zip = self.client.get("/api/reports/monthly/zip?month=2026-11", headers=self.admin_headers)
        self.assertEqual(res_zip.status_code, 200)
        self.assertEqual(res_zip.headers["content-type"], "application/zip")
        self.assertTrue(res_zip.content.startswith(b"PK"))

    def test_consecutive_months_balance_rollover(self):
        # Initial balance 5000
        # Post payment of 400 in October 2026
        self._post_employee_request(amount="400.00", req_date="2026-10-10", post_date="2026-10-12")
        # Post receipt of 1000 in October 2026
        create_company_receipt(
            self.admin["id"],
            1000.00,
            "2026-10-15",
            "October replenishment",
            self.ledger_office["id"],
            "Replenishment",
            self.project_a["id"],
        )

        # October report
        oct_data = get_monthly_report_data("2026-10")
        self.assertEqual(oct_data["opening_balance"], 5000.00)
        self.assertEqual(oct_data["total_payments"], 400.00)
        self.assertEqual(oct_data["total_receipts"], 1000.00)
        self.assertEqual(oct_data["closing_balance"], 5600.00)

        # Post payment of 600 in November 2026
        self._post_employee_request(amount="600.00", req_date="2026-11-02", post_date="2026-11-04")

        # November report: Opening balance MUST EQUAL October's closing balance (5600.00)
        nov_data = get_monthly_report_data("2026-11")
        self.assertEqual(nov_data["opening_balance"], 5600.00)
        self.assertEqual(nov_data["total_payments"], 600.00)
        self.assertEqual(nov_data["closing_balance"], 5000.00)

    def test_company_receipts_direct_posting_and_presence_in_reports(self):
        # 1. Admin fills company receipt with minimal fields: amount, date, description
        payload = {
            "amount": 750.00,
            "date": "2026-11-18",
            "description": "Cash replenishment by Director",
        }

        # Check balance before
        with database.get_connection() as conn:
            bal_before = conn.execute(
                "SELECT current_balance FROM cash_account_balances WHERE cash_account_id='system-main-cash'"
            ).fetchone()[0]

        # Post receipt directly via API
        res = self.client.post("/api/company-receipts", json=payload, headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        receipt_data = res.json()
        self.assertIsNotNone(receipt_data.get("id"))
        self.assertIsNotNone(receipt_data.get("ledger_entry_id"))
        self.assertEqual(float(receipt_data["amount"]), 750.00)

        # Verify balance updated DIRECTLY
        with database.get_connection() as conn:
            bal_after = conn.execute(
                "SELECT current_balance FROM cash_account_balances WHERE cash_account_id='system-main-cash'"
            ).fetchone()[0]
            entry = conn.execute(
                "SELECT * FROM ledger_entries WHERE id = ?",
                (receipt_data["ledger_entry_id"],),
            ).fetchone()

        self.assertEqual(float(bal_after), float(bal_before) + 750.00)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["entry_type"], "RECEIPT")
        self.assertEqual(float(entry["amount"]), 750.00)

        # 2. Verify receipt is present in monthly report API
        report_res = self.client.get("/api/reports/monthly?month=2026-11", headers=self.admin_headers)
        self.assertEqual(report_res.status_code, 200)
        report_json = report_res.json()

        # Present in total_receipts
        self.assertGreaterEqual(report_json["total_receipts"], 750.00)

        # Present in posted_entries
        receipt_entries = [e for e in report_json["posted_entries"] if e.get("receipt") == 750.00]
        self.assertEqual(len(receipt_entries), 1)
        r_entry = receipt_entries[0]
        self.assertEqual(r_entry["date"], "2026-11-18")
        self.assertEqual(r_entry["requested_by"], "Company")
        self.assertEqual(r_entry["description"], "Cash replenishment by Director")

        # Present in company_receipts list
        matching_cr = [cr for cr in report_json.get("company_receipts", []) if cr.get("receipt") == 750.00]
        self.assertEqual(len(matching_cr), 1)

        # Present in daily movement
        day_18 = next((d for d in report_json["daily_movement"] if d["date"] == "2026-11-18"), None)
        self.assertIsNotNone(day_18)
        self.assertGreaterEqual(day_18["receipts"], 750.00)

        # 3. Verify receipt is present in Excel export
        excel_res = self.client.get("/api/reports/monthly/excel?month=2026-11", headers=self.admin_headers)
        self.assertEqual(excel_res.status_code, 200)
        wb = openpyxl.load_workbook(io.BytesIO(excel_res.content))
        ws_tx = wb["Petty Cash Sheet"]

        # Search for row with 750 in Column 4 (Receipt)
        found_receipt_row = False
        for row in range(2, ws_tx.max_row + 1):
            if ws_tx.cell(row, 4).value == 750.00:
                found_receipt_row = True
                self.assertEqual(ws_tx.cell(row, 1).value, "2026-11-18")
                self.assertEqual(ws_tx.cell(row, 3).value, "Cash replenishment by Director")
                self.assertEqual(ws_tx.cell(row, 8).value, "Company")
                break
        self.assertTrue(found_receipt_row, "Company receipt row not found in Petty Cash Sheet")


if __name__ == "__main__":
    unittest.main()
