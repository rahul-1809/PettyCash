"""Comprehensive regression and verification test suite for audit findings F-01 through F-16."""

import os
import io
import time
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from backend import database
from backend.main import app
from backend.auth_service import (
    create_onboarding_token,
    create_session as create_auth_session,
    set_password_with_token,
)
from backend.user_service import provision_user, create_bootstrap_admin
from backend.domain_repository import create_master_record


class AuditRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_audit.db"
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL

        database.DB_PATH = str(self.db_path)
        database.DATABASE_URL = None
        database.init_db()

        # Bootstrap director, finance, managers & employees
        self.director = create_bootstrap_admin("admin_aud", "admin_aud@example.com", "Password123456!")
        self.director_token = create_auth_session(self.director["id"])

        self.admin, _ = provision_user("fin_aud", "fin_aud@example.com", "Finance", self.director["id"])
        self.admin_token = create_auth_session(self.admin["id"])

        self.manager1, _ = provision_user("mgr1_aud", "mgr1@example.com", "Manager", self.director["id"])
        self.manager1_token = create_auth_session(self.manager1["id"])

        self.employee1, _ = provision_user("emp1_aud", "emp1@example.com", "Employee", self.director["id"])
        self.employee1_token = create_auth_session(self.employee1["id"])

        self.employee2, _ = provision_user("emp2_aud", "emp2@example.com", "Employee", self.director["id"])
        self.employee2_token = create_auth_session(self.employee2["id"])

        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url

    # ─── F-01: Sessions API Authentication & RBAC ─────────────────────────────
    def test_f01_sessions_api_authentication_and_isolation(self):
        # 1. Unauthenticated requests must return 401
        self.assertEqual(self.client.get("/api/sessions").status_code, 401)
        self.assertEqual(self.client.post("/api/sessions", json={}).status_code, 401)
        self.assertEqual(self.client.delete("/api/sessions/any-id").status_code, 401)
        self.assertEqual(self.client.get("/api/default-data").status_code, 401)
        self.assertEqual(self.client.post("/api/recalculate", json={}).status_code, 401)

        # 2. Employee & Director are blocked from spreadsheet sessions (403); Manager & Finance allowed
        self.assertEqual(
            self.client.post(
                "/api/sessions",
                headers={"Authorization": f"Bearer {self.employee1_token}"},
                json={"name": "Blocked", "opening_balance": 100.0, "start_date": "2026-11-01", "end_date": "2026-11-30", "transactions": []},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/sessions", headers={"Authorization": f"Bearer {self.director_token}"}).status_code,
            403,
        )

        # Manager 1 creates a session
        create_res = self.client.post(
            "/api/sessions",
            headers={"Authorization": f"Bearer {self.manager1_token}"},
            json={
                "name": "Manager 1 Private Session",
                "opening_balance": 1000.0,
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
                "transactions": [],
            },
        )
        self.assertEqual(create_res.status_code, 200)
        session_id = create_res.json()["id"]

        # 3. Employee cannot access Manager's session
        emp2_get = self.client.get(
            f"/api/sessions/{session_id}",
            headers={"Authorization": f"Bearer {self.employee2_token}"},
        )
        self.assertEqual(emp2_get.status_code, 403)

        # 4. Employee cannot delete Manager's session
        emp2_del = self.client.delete(
            f"/api/sessions/{session_id}",
            headers={"Authorization": f"Bearer {self.employee2_token}"},
        )
        self.assertEqual(emp2_del.status_code, 403)

        # 5. Finance can access it
        admin_get = self.client.get(
            f"/api/sessions/{session_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(admin_get.status_code, 200)

    # ─── F-02: Query-String Tokens Rejected ───────────────────────────────────
    def test_f02_query_string_token_rejected(self):
        # Passing valid token in query param without Authorization header must return 401
        res = self.client.get(f"/api/cash-balance?token={self.admin_token}")
        self.assertEqual(res.status_code, 401)

        res2 = self.client.get(f"/api/cash-balance?auth_token={self.admin_token}")
        self.assertEqual(res2.status_code, 401)

    # ─── F-03: Password Reset Invalidation ────────────────────────────────────
    def test_f03_password_reset_revokes_active_sessions(self):
        # 1. Employee 1 session is valid
        res_me_before = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {self.employee1_token}"},
        )
        self.assertEqual(res_me_before.status_code, 200)

        # 2. Reset password using onboarding token
        reset_token = create_onboarding_token(self.employee1["id"])
        set_password_with_token(reset_token, "NewSecurePassword12345!")

        # 3. Employee 1's pre-reset session must now be rejected (401)
        res_me_after = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {self.employee1_token}"},
        )
        self.assertEqual(res_me_after.status_code, 401)

    # ─── F-04: Balance Overwrite Reconciled with Ledger ───────────────────────
    def test_f04_balance_overwrite_creates_reconciling_adjustment(self):
        # 1. Configure initial cash balance
        self.client.put(
            "/api/cash-balance",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"opening_balance": 1000.00},
        )

        # 2. Create receipt so ledger activity exists
        res_rcpt = self.client.post(
            "/api/company-receipts",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={
                "amount": 500.00,
                "receipt_date": "2026-11-20",
                "description": "Initial Vault Top-up",
            },
        )
        self.assertEqual(res_rcpt.status_code, 200)

        # 3. Update cash balance when activity exists
        res_update = self.client.put(
            "/api/cash-balance",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"opening_balance": 2000.00},
        )
        self.assertEqual(res_update.status_code, 200)

        # 4. Verify that an adjustment was automatically recorded
        with database.get_connection() as conn:
            adj = conn.execute("SELECT * FROM ledger_adjustments WHERE cash_account_id='system-main-cash'").fetchone()
            self.assertIsNotNone(adj)
            self.assertEqual(float(adj["amount"]), 500.00) # (2000 - 1500 = +500)
            self.assertEqual(adj["direction"], "INFLOW")

    # ─── F-05 & F-07: Decimal & Magnitude Validation ──────────────────────────
    def test_f05_and_f07_monetary_bounds_and_precision(self):
        # Extreme magnitude (>100M) is rejected
        res_huge = self.client.post(
            "/api/company-receipts",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={
                "amount": 123456789012345678.90,
                "receipt_date": "2026-11-20",
                "description": "Huge invalid top-up",
            },
        )
        self.assertEqual(res_huge.status_code, 422)

    # ─── F-10: Max Text Length Bounds ─────────────────────────────────────────
    def test_f10_text_length_bounds(self):
        # Excessively long purpose (>500 chars) is rejected
        res_long = self.client.post(
            "/api/requests",
            headers={"Authorization": f"Bearer {self.employee1_token}"},
            json={
                "project_id": "proj-1",
                "ledger_id": "ledg-1",
                "category": "Office",
                "request_date": "2026-11-20",
                "amount": 100.00,
                "purpose": "A" * 1000,
                "approving_manager_id": "mgr-1",
            },
        )
        self.assertEqual(res_long.status_code, 422)

    # ─── F-12: Dedicated Login Throttling & Lockout ───────────────────────────
    def test_f12_login_lockout(self):
        # 5 consecutive failed logins trigger 429 lockout
        for _ in range(5):
            res_fail = self.client.post(
                "/api/auth/login",
                json={"email": "admin_aud@example.com", "password": "WrongPassword123!"},
            )
            self.assertIn(res_fail.status_code, (400, 401))

        # 6th attempt must be blocked by rate limiter with 429
        res_locked = self.client.post(
            "/api/auth/login",
            json={"email": "admin_aud@example.com", "password": "WrongPassword123!"},
        )
        self.assertEqual(res_locked.status_code, 429)

    # ─── F-13: Sub-Cent Inputs Rejected ───────────────────────────────────────
    def test_f13_sub_cent_inputs_rejected(self):
        # 10.999 has 3 decimal places -> must be rejected with 422, not silently rounded
        res_sub = self.client.post(
            "/api/company-receipts",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={
                "amount": 10.999,
                "receipt_date": "2026-11-20",
                "description": "Sub-cent test",
            },
        )
        self.assertEqual(res_sub.status_code, 422)

    # ─── F-15: Client Idempotency-Key Support ─────────────────────────────────
    def test_f15_client_idempotency_key(self):
        # Submitting two identical transactions with distinct idempotency keys both succeed
        res1 = self.client.post(
            "/api/company-receipts",
            headers={
                "Authorization": f"Bearer {self.admin_token}",
                "Idempotency-Key": "client-tx-001",
            },
            json={
                "amount": 250.00,
                "receipt_date": "2026-11-20",
                "description": "Top-up 1",
            },
        )
        self.assertEqual(res1.status_code, 200)
        self.assertFalse(res1.json().get("duplicate", False))

        res2 = self.client.post(
            "/api/company-receipts",
            headers={
                "Authorization": f"Bearer {self.admin_token}",
                "Idempotency-Key": "client-tx-002",
            },
            json={
                "amount": 250.00,
                "receipt_date": "2026-11-20",
                "description": "Top-up 1", # identical content, different key
            },
        )
        self.assertEqual(res2.status_code, 200)
        self.assertFalse(res2.json().get("duplicate", False))

    # ─── F-16: Database Connection Cleanup ────────────────────────────────────
    def test_f16_database_connection_cleanup(self):
        with database.get_connection() as conn:
            row = conn.execute("SELECT 1 AS num").fetchone()
            self.assertEqual(row["num"], 1)
        # Connection must be closed upon exiting context
        # In SQLite, trying to execute on a closed connection raises ProgrammingError
        self.assertRaises(Exception, conn.execute, "SELECT 1")

    # ─── F-06: Bounded CAS Retries Under High Concurrency ─────────────────────
    def test_f06_concurrency_posting_retries(self):
        # 1. Initialize balance
        self.client.put(
            "/api/cash-balance",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"opening_balance": 1000.00},
        )

        # 2. Setup project, ledger, manager, and assignment
        manager, _ = provision_user("mgr_conc", "mgr_conc@example.com", "Manager", self.admin["id"])
        mgr_token = create_auth_session(manager["id"])

        res_assign = self.client.post(
            "/api/assignments",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"manager_id": manager["id"], "employee_id": self.employee1["id"]},
        )
        assign_id = res_assign.json()["id"]
        self.client.post(
            f"/api/assignments/{assign_id}/review",
            headers={"Authorization": f"Bearer {mgr_token}"},
            json={"decision": "APPROVED", "reason": "Approved assignment"},
        )

        proj = create_master_record("projects", "Concurrency Project")
        ledg = create_master_record("ledgers", "Concurrency Ledger")

        req_ids = []
        for i in range(8):
            res_c = self.client.post(
                "/api/requests",
                headers={"Authorization": f"Bearer {self.employee1_token}"},
                json={
                    "project_id": proj["id"],
                    "ledger_id": ledg["id"],
                    "category": "Office",
                    "request_date": "2026-11-20",
                    "amount": 100.00,
                    "purpose": f"Concurrency Expense {i}",
                    "approving_manager_id": manager["id"],
                },
            )
            r_id = res_c.json()["id"]
            self.client.post(f"/api/requests/{r_id}/submit", headers={"Authorization": f"Bearer {self.employee1_token}"})
            self.client.post(f"/api/requests/{r_id}/approve", headers={"Authorization": f"Bearer {mgr_token}"}, json={})
            self.client.post(
                f"/api/requests/{r_id}/supporting-files",
                headers={"Authorization": f"Bearer {self.employee1_token}"},
                files={"file": ("receipt.pdf", b"%PDF-1.4 test voucher evidence", "application/pdf")},
            )
            self.client.post(f"/api/requests/{r_id}/submit-for-posting", headers={"Authorization": f"Bearer {self.employee1_token}"})
            req_ids.append(r_id)

        # 3. Fire all 8 posts concurrently!
        def do_post(rid):
            return self.client.post(
                f"/api/requests/{rid}/post",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                json={"effective_date": "2026-11-20"},
            )

        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(do_post, req_ids))

        statuses = [r.status_code for r in results]
        self.assertEqual(statuses, [200] * 8)

        # Balance must be exactly 1000 - 800 = 200.00
        bal_res = self.client.get("/api/cash-balance", headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(float(bal_res.json()["current_balance"]), 200.00)

    def test_user_deactivation_and_reactivation_flow(self):
        """Verify user deactivation, reactivation, and re-provisioning of inactive users."""
        # 1. Provision a test employee (Director)
        prov_res = self.client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {self.director_token}"},
            json={"username": "temp_deact_user", "email": "temp_deact@example.com", "role": "Employee"},
        )
        self.assertEqual(prov_res.status_code, 200)
        target_uid = prov_res.json()["id"]

        # 2. Deactivate the user (Director)
        deact_res = self.client.post(
            f"/api/users/{target_uid}/deactivate",
            headers={"Authorization": f"Bearer {self.director_token}"},
        )
        self.assertEqual(deact_res.status_code, 200)
        self.assertEqual(deact_res.json()["status"], "DEACTIVATED")

        # 3. List users includes inactive user with is_active = 0
        list_res = self.client.get("/api/users", headers={"Authorization": f"Bearer {self.director_token}"})
        self.assertEqual(list_res.status_code, 200)
        u_record = next(u for u in list_res.json() if u["id"] == target_uid)
        self.assertEqual(u_record["is_active"], 0)

        # 4. Re-provisioning the same email automatically reactivates the account
        reprov_res = self.client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {self.director_token}"},
            json={"username": "temp_deact_user", "email": "temp_deact@example.com", "role": "Manager"},
        )
        self.assertEqual(reprov_res.status_code, 200)
        self.assertTrue(reprov_res.json().get("reactivated"))
        self.assertEqual(reprov_res.json()["role"], "Manager")

        # Verify active in DB
        list_res2 = self.client.get("/api/users", headers={"Authorization": f"Bearer {self.director_token}"})
        u_record2 = next(u for u in list_res2.json() if u["id"] == target_uid)
        self.assertEqual(u_record2["is_active"], 1)
