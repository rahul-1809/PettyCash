import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend import database
from backend.auth_service import create_session as create_auth_session
from backend.domain_repository import create_master_record
from backend.main import app
from backend.notification_service import list_notifications
from backend.user_service import (
    create_assignment,
    create_bootstrap_admin,
    create_finance_assignment,
    provision_user,
    review_assignment,
)


class FinanceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "finance_workflow.sqlite")
        database.DATABASE_URL = None
        os.environ["SUPPORTING_FILES_DIR"] = str(Path(self.temp_dir.name) / "storage")
        database.init_db()

        # 1. Provision all 4 roles
        self.director = create_bootstrap_admin("dir_user", "director@example.com", "DirPassword123!")
        self.director_token = create_auth_session(self.director["id"])
        self.director_headers = {"Authorization": f"Bearer {self.director_token}"}

        self.finance, _ = provision_user("fin_user", "finance@example.com", "Finance", self.director["id"])
        self.finance_token = create_auth_session(self.finance["id"])
        self.finance_headers = {"Authorization": f"Bearer {self.finance_token}"}

        self.manager, _ = provision_user("mgr_user", "manager@example.com", "Manager", self.director["id"])
        self.manager_token = create_auth_session(self.manager["id"])
        self.manager_headers = {"Authorization": f"Bearer {self.manager_token}"}

        self.employee, _ = provision_user("emp_user", "employee@example.com", "Employee", self.director["id"])
        self.employee_token = create_auth_session(self.employee["id"])
        self.employee_headers = {"Authorization": f"Bearer {self.employee_token}"}

        # 2. Assign Manager -> Employee (Finance creates assignment)
        asgn = create_assignment(self.manager["id"], self.employee["id"], self.finance["id"])
        review_assignment(asgn["id"], self.manager["id"], "APPROVED")

        # 3. Master data & initial balance
        self.project = create_master_record("projects", "Expansion")
        self.ledger = create_master_record("ledgers", "Operations")

        marker = database._placeholder()
        with database.get_connection() as conn:
            conn.execute(
                f"UPDATE cash_account_balances SET current_balance={marker} WHERE cash_account_id='system-main-cash'",
                ("10000.00",),
            )
            conn.commit()

        from backend.observability import _LOGIN_ATTEMPTS, _LOGIN_LOCKOUTS
        _LOGIN_ATTEMPTS.clear()
        _LOGIN_LOCKOUTS.clear()
        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url

    def test_01_director_finance_manager_rbac_boundaries(self):
        # Director is blocked from Finance-only & Spreadsheet operations
        self.assertEqual(
            self.client.post("/api/projects", headers=self.director_headers, json={"name": "Blocked"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/assignments", headers=self.director_headers, json={"manager_id": self.manager["id"], "employee_id": self.employee["id"]}).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/sessions", headers=self.director_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/company-receipts", headers=self.director_headers).status_code, 403)

        # Director CAN view reports and ZIP exports
        self.assertEqual(self.client.get("/api/reports/monthly?month=2026-11", headers=self.director_headers).status_code, 200)
        self.assertEqual(self.client.get("/api/reports/monthly/zip?month=2026-11", headers=self.director_headers).status_code, 200)

        # Finance is blocked from Director-only user provisioning & audit events
        self.assertEqual(
            self.client.post("/api/users", headers=self.finance_headers, json={"username": "x", "email": "x@x.com", "role": "Employee"}).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/audit-events", headers=self.finance_headers).status_code, 403)

        # Manager CAN view reports and ZIP exports
        self.assertEqual(self.client.get("/api/reports/monthly?month=2026-11", headers=self.manager_headers).status_code, 200)
        self.assertEqual(self.client.get("/api/reports/monthly/zip?month=2026-11", headers=self.manager_headers).status_code, 200)

    def test_02_case1_employee_request_direct_post_and_late_voucher(self):
        # Assign Finance -> Manager
        create_finance_assignment(self.finance["id"], self.manager["id"], self.finance["id"])

        # Employee creates & submits request
        create_res = self.client.post(
            "/api/requests",
            headers=self.employee_headers,
            json={
                "project_id": self.project["id"],
                "ledger_id": self.ledger["id"],
                "category": "Travel",
                "request_date": "2026-11-15",
                "amount": 250.0,
                "purpose": "Client travel",
                "approving_manager_id": self.manager["id"],
            },
        )
        self.assertEqual(create_res.status_code, 200)
        req_id = create_res.json()["id"]
        self.assertEqual(self.client.post(f"/api/requests/{req_id}/submit", headers=self.employee_headers).status_code, 200)

        # Manager approves -> goes straight to Finance posting queue
        self.assertEqual(self.client.post(f"/api/requests/{req_id}/approve", headers=self.manager_headers).status_code, 200)

        # Finance posts directly WITHOUT any voucher uploaded yet!
        post_res = self.client.post(
            f"/api/requests/{req_id}/post",
            headers=self.finance_headers,
            json={"effective_date": "2026-11-15"},
        )
        self.assertEqual(post_res.status_code, 200)
        self.assertEqual(post_res.json()["status"], "POSTED")

        # Report shows Posted (Voucher Pending)
        rep1 = self.client.get("/api/reports/monthly?month=2026-11", headers=self.finance_headers).json()
        tx1 = next(t for t in rep1["posted_entries"] if t.get("request_id") == req_id)
        self.assertEqual(tx1["voucher_status"], "Posted (Voucher Pending)")

        # Employee uploads supporting voucher AFTER posting
        up_res = self.client.post(
            f"/api/requests/{req_id}/supporting-files",
            headers=self.employee_headers,
            files={"file": ("cab_receipt.pdf", b"%PDF-1.4 receipt content", "application/pdf")},
        )
        self.assertEqual(up_res.status_code, 200)

        # Report immediately reflects Posted (Voucher Attached)
        rep2 = self.client.get("/api/reports/monthly?month=2026-11", headers=self.finance_headers).json()
        tx2 = next(t for t in rep2["posted_entries"] if t.get("request_id") == req_id)
        self.assertEqual(tx2["voucher_status"], "Posted (Voucher Attached)")
        self.assertEqual(tx2["supporting_count"], 1)

        # Director received ZERO unnecessary transactional notifications!
        dir_notifs = list_notifications(self.director["id"])
        self.assertEqual(len(dir_notifs), 0)

        # Finance received actionable notifications (ready for posting + voucher uploaded)
        fin_notifs = [n["event_type"] for n in list_notifications(self.finance["id"])]
        self.assertIn("REQUEST_READY_FOR_POSTING", fin_notifs)
        self.assertIn("VOUCHER_UPLOADED", fin_notifs)

    def test_03_case2_manager_request_requires_assignment_and_late_voucher(self):
        # Unassigned manager is rejected
        unassigned_res = self.client.post(
            "/api/requests",
            headers=self.manager_headers,
            json={
                "project_id": self.project["id"],
                "ledger_id": self.ledger["id"],
                "category": "Meals",
                "request_date": "2026-11-16",
                "amount": 500.0,
                "purpose": "Team lunch",
            },
        )
        self.assertEqual(unassigned_res.status_code, 400)

        # Finance assigns Finance <-> Manager via API
        asgn_res = self.client.post(
            "/api/finance-assignments",
            headers=self.finance_headers,
            json={"finance_user_id": self.finance["id"], "manager_id": self.manager["id"]},
        )
        self.assertEqual(asgn_res.status_code, 200)

        # Manager raises request -> submits -> enters Finance posting queue directly
        mgr_req = self.client.post(
            "/api/requests",
            headers=self.manager_headers,
            json={
                "project_id": self.project["id"],
                "ledger_id": self.ledger["id"],
                "category": "Meals",
                "request_date": "2026-11-16",
                "amount": 500.0,
                "purpose": "Team lunch",
            },
        )
        self.assertEqual(mgr_req.status_code, 200)
        req_id = mgr_req.json()["id"]
        sub_res = self.client.post(f"/api/requests/{req_id}/submit", headers=self.manager_headers)
        self.assertEqual(sub_res.status_code, 200)
        self.assertEqual(sub_res.json()["status"], "APPROVED")

        # Finance posts it
        post_res = self.client.post(
            f"/api/requests/{req_id}/post",
            headers=self.finance_headers,
            json={"effective_date": "2026-11-16"},
        )
        self.assertEqual(post_res.status_code, 200)

        # Manager uploads voucher after posting
        up_res = self.client.post(
            f"/api/requests/{req_id}/supporting-files",
            headers=self.manager_headers,
            files={"file": ("lunch_bill.pdf", b"%PDF-1.4 lunch bill", "application/pdf")},
        )
        self.assertEqual(up_res.status_code, 200)

        rep = self.client.get("/api/reports/monthly?month=2026-11", headers=self.manager_headers).json()
        tx = next(t for t in rep["posted_entries"] if t.get("request_id") == req_id)
        self.assertEqual(tx["voucher_status"], "Posted (Voucher Attached)")

    def test_04_case3_finance_direct_expense_and_late_voucher(self):
        res = self.client.post(
            "/api/finance/direct-expense",
            headers=self.finance_headers,
            json={
                "project_id": self.project["id"],
                "ledger_id": self.ledger["id"],
                "category": "Supplies",
                "effective_date": "2026-11-18",
                "amount": 1200.0,
                "purpose": "Printer toner purchase",
            },
        )
        self.assertEqual(res.status_code, 200)
        req_id = res.json()["request_id"]
        self.assertEqual(res.json()["status"], "POSTED")

        # Balance deducted immediately (10000 - 1200 = 8800)
        bal = self.client.get("/api/cash-balance", headers=self.finance_headers).json()
        self.assertEqual(float(bal["current_balance"]), 8800.00)

        # Finance uploads voucher later
        up_res = self.client.post(
            f"/api/requests/{req_id}/supporting-files",
            headers=self.finance_headers,
            files={"file": ("toner_inv.pdf", b"%PDF-1.4 toner invoice", "application/pdf")},
        )
        self.assertEqual(up_res.status_code, 200)

        rep = self.client.get("/api/reports/monthly?month=2026-11", headers=self.finance_headers).json()
        tx = next(t for t in rep["posted_entries"] if t.get("request_id") == req_id)
        self.assertEqual(tx["voucher_status"], "Posted (Voucher Attached)")

    def test_05_universal_change_password(self):
        # Wrong current password rejected
        bad = self.client.post(
            "/api/auth/change-password",
            headers=self.director_headers,
            json={"current_password": "WrongPassword!", "new_password": "NewStrongPassword123!"},
        )
        self.assertEqual(bad.status_code, 400)

        # Valid password change succeeds
        ok = self.client.post(
            "/api/auth/change-password",
            headers=self.director_headers,
            json={"current_password": "DirPassword123!", "new_password": "NewStrongPassword123!"},
        )
        self.assertEqual(ok.status_code, 200)

        # Old password fails login, new password succeeds
        self.assertEqual(
            self.client.post("/api/auth/login", json={"email": "director@example.com", "password": "DirPassword123!"}).status_code,
            401,
        )
        self.assertEqual(
            self.client.post("/api/auth/login", json={"email": "director@example.com", "password": "NewStrongPassword123!"}).status_code,
            200,
        )

    def test_06_finance_can_set_negative_opening_balance(self):
        res = self.client.put(
            "/api/cash-balance",
            headers=self.finance_headers,
            json={"opening_balance": -2500.50},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(float(res.json()["opening_balance"]), -2500.50)
        self.assertEqual(float(res.json()["current_balance"]), -2500.50)


if __name__ == "__main__":
    unittest.main()
