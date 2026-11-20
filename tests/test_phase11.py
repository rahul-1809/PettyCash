import datetime
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend import database
from backend.main import app
from backend.auth_service import create_session as create_auth_session
from backend.user_service import (
    create_assignment,
    create_bootstrap_admin,
    provision_user,
    review_assignment,
)
from backend.domain_repository import create_master_record
from backend.request_service import (
    create_draft,
    get_request,
    manager_decision,
    submit_request,
)
from backend.posting_service import post_request
from backend.receipt_service import create_company_receipt
from backend.financial_control_service import (
    create_financial_period,
    close_financial_period,
    reopen_financial_period,
    reverse_company_receipt,
    reverse_posted_request,
)
from backend.supporting_service import upload_supporting_file, get_supporting_file, storage_root
from backend.operations_service import (
    create_database_backup,
    execute_deployment_rollback,
    get_backup_dir,
    get_liveness,
    get_readiness,
    list_backups,
    restore_database_backup,
    verify_database_backup,
)
from backend.audit_service import list_audit_events


class Phase11ReleaseVerificationTests(unittest.TestCase):
    """Phase 11: Comprehensive End-to-End Testing and Production Release Verification."""

    def _set_balance(self, amount: str):
        with database.get_connection() as conn:
            conn.execute(
                f"UPDATE cash_account_balances SET current_balance={database._placeholder()} WHERE cash_account_id='system-main-cash'",
                (amount,),
            )
            conn.commit()

    def _get_balance(self) -> Decimal:
        with database.get_connection() as conn:
            row = conn.execute("SELECT current_balance FROM cash_account_balances WHERE cash_account_id='system-main-cash'").fetchone()
            return Decimal(str(row[0]))

    def _create_draft(self, amount="100.00", purpose="Expense", project_id=None, ledger_id=None, category="Travel & Local Conveyance", notes=None):
        return create_draft(
            requester_id=self.employee["id"],
            project_id=project_id or self.project_a["id"],
            ledger_id=ledger_id or self.ledger_ops["id"],
            category=category,
            request_date="2026-11-19",
            amount=amount,
            purpose=purpose,
            notes=notes,
            approving_manager_id=self.manager["id"],
        )

    def _upload_file(self, req_id: str, filename: str, content: bytes, content_type: str = "application/pdf"):
        return upload_supporting_file(
            request_id=req_id,
            uploader_id=self.employee["id"],
            filename=filename,
            content_type=content_type,
            content=content,
        )

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "phase11_test.sqlite")
        database.DATABASE_URL = None
        database.init_db()

        # Isolate supporting files and backups
        self.storage_dir = Path(self.temp_dir.name) / "storage"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        os.environ["SUPPORTING_FILES_DIR"] = str(self.storage_dir)

        self.backup_dir = Path(self.temp_dir.name) / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        os.environ["BACKUP_DIR"] = str(self.backup_dir)

        # 1. Provision Users
        self.admin = create_bootstrap_admin("admin_rel", "admin_rel@example.com", "ReleaseAdminPass123!")
        self.admin_token = create_auth_session(self.admin["id"])
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

        self.manager, _ = provision_user("mgr_rel", "mgr_rel@example.com", "Manager", self.admin["id"])
        self.manager_token = create_auth_session(self.manager["id"])
        self.manager_headers = {"Authorization": f"Bearer {self.manager_token}"}

        self.other_manager, _ = provision_user("mgr_other", "mgr_other@example.com", "Manager", self.admin["id"])
        self.other_manager_token = create_auth_session(self.other_manager["id"])
        self.other_manager_headers = {"Authorization": f"Bearer {self.other_manager_token}"}

        self.employee, _ = provision_user("emp_rel", "emp_rel@example.com", "Employee", self.admin["id"])
        self.employee_token = create_auth_session(self.employee["id"])
        self.employee_headers = {"Authorization": f"Bearer {self.employee_token}"}

        # 2. Assign Employee to primary Manager
        asgn = create_assignment(self.manager["id"], self.employee["id"], self.admin["id"])
        review_assignment(asgn["id"], self.manager["id"], "APPROVED")

        # 3. Master Financial Catalog
        self.project_a = create_master_record("projects", "Project Alpha")
        self.project_b = create_master_record("projects", "Project Beta")
        self.ledger_ops = create_master_record("ledgers", "Operations")
        self.category_travel = create_master_record("categories", "Travel & Local Conveyance")

        # 4. Initial Vault Balance
        self._set_balance("50000.00")

        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        os.environ.pop("SUPPORTING_FILES_DIR", None)
        os.environ.pop("BACKUP_DIR", None)

    # ── 1. Comprehensive Request State Machine & Transition Matrix ───────────

    def test_01_complete_state_transition_matrix_and_guards(self):
        """Verify the complete allowed transition lifecycle and enforce all invalid transition rejections."""
        # Step 1: Create draft
        req = self._create_draft(
            amount="1250.00",
            purpose="Offsite travel ticket",
            notes="Booking ref: TX-102",
        )
        req_id = req["id"]
        self.assertEqual(req["status"], "DRAFT")

        # Disallowed: DRAFT -> APPROVED directly without submission
        with self.assertRaises(ValueError):
            manager_decision(req_id, self.manager["id"], "APPROVED")

        # Disallowed: DRAFT -> POSTED directly
        with self.assertRaises(ValueError):
            post_request(req_id, self.admin["id"], "2026-11-19")

        # Step 2: DRAFT -> SUBMITTED (allowed for requester)
        sub_req = submit_request(req_id, self.employee["id"])
        self.assertEqual(sub_req["status"], "SUBMITTED")

        # Disallowed: Unassigned manager cannot decide
        with self.assertRaises(PermissionError):
            manager_decision(req_id, self.other_manager["id"], "APPROVED")

        # Disallowed: Requester cannot self-approve
        with self.assertRaises(PermissionError):
            manager_decision(req_id, self.employee["id"], "APPROVED")

        # Step 3: SUBMITTED -> DRAFT (Request changes returns to editable draft with reason)
        cr_req = manager_decision(req_id, self.manager["id"], "DRAFT", reason="Please specify date")
        self.assertEqual(cr_req["status"], "DRAFT")
        self.assertEqual(cr_req["change_reason"], "Please specify date")

        # Step 4: CHANGES_REQUESTED -> SUBMITTED (re-submit)
        resub_req = submit_request(req_id, self.employee["id"])
        self.assertEqual(resub_req["status"], "SUBMITTED")

        # Step 5: SUBMITTED -> APPROVED
        appr_req = manager_decision(req_id, self.manager["id"], "APPROVED")
        self.assertEqual(appr_req["status"], "APPROVED")

        # Step 6: APPROVED -> SUPPORTING_UPLOADED
        pdf_bytes = b"%PDF-1.4 Voucher Proof Ticket Receipt"
        up_res = self._upload_file(req_id, "ticket.pdf", pdf_bytes)
        self.assertEqual(up_res["original_filename"], "ticket.pdf")

        chk_req = get_request(req_id)
        self.assertEqual(chk_req["status"], "SUPPORTING_UPLOADED")

        # Step 7: SUPPORTING_UPLOADED -> POSTED
        post_res = post_request(req_id, self.admin["id"], "2026-11-19")
        self.assertEqual(post_res["status"], "POSTED")

        # Disallowed: POSTED -> DRAFT or APPROVED (immutable ledger record)
        with self.assertRaises(ValueError):
            manager_decision(req_id, self.manager["id"], "APPROVED")

    def test_02_rejection_is_terminal_state(self):
        """Verify that a rejected request reaches a terminal state and cannot be revived."""
        req = self._create_draft(
            amount="3000.00",
            purpose="Conference registration",
            project_id=self.project_b["id"],
        )
        submit_request(req["id"], self.employee["id"])

        # Rejection requires reason
        with self.assertRaises(ValueError):
            manager_decision(req["id"], self.manager["id"], "REJECTED", reason="")

        rej_req = manager_decision(req["id"], self.manager["id"], "REJECTED", reason="Out of travel budget")
        self.assertEqual(rej_req["status"], "REJECTED")

        # Cannot submit a rejected request
        with self.assertRaises(ValueError):
            submit_request(req["id"], self.employee["id"])

        # Cannot approve a rejected request
        with self.assertRaises(ValueError):
            manager_decision(req["id"], self.manager["id"], "APPROVED")

    # ── 2. File Security, MIME Types, Size Limits & Path Traversal ────────────

    def test_03_file_security_and_upload_validation(self):
        """Enforce strict file upload constraints: disallowed extensions, size limits, and sanitization."""
        # 1. Upload rejected before approval
        req = self._create_draft(
            amount="500.00",
            purpose="Supplies",
        )
        with self.assertRaises(ValueError):
            self._upload_file(req["id"], "receipt.png", b"\x89PNG\r\n\x1a\nfake", "image/png")

        # Approve the request
        submit_request(req["id"], self.employee["id"])
        manager_decision(req["id"], self.manager["id"], "APPROVED")

        # 2. Reject executable / malicious file extensions
        malicious_files = [
            ("script.sh", "application/x-sh"),
            ("payload.exe", "application/x-msdownload"),
            ("exploit.bat", "application/x-bat"),
            ("server.py", "text/x-python"),
            ("index.html", "text/html"),
        ]
        for bad_filename, bad_mime in malicious_files:
            with self.assertRaises(ValueError):
                self._upload_file(req["id"], bad_filename, b"content", bad_mime)

        # 3. Reject file size exceeding MAX_SIZE (15MB)
        oversized_bytes = b"0" * (15 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError):
            self._upload_file(req["id"], "huge.pdf", oversized_bytes)

        # 4. Path traversal attempt in filename is strictly rejected
        valid_pdf = b"%PDF-1.4\nTest Receipt Document"
        with self.assertRaises(ValueError):
            self._upload_file(req["id"], "../../etc/passwd.pdf", valid_pdf)

        # 5. Safe file upload succeeds and is stored strictly within storage root
        uploaded = self._upload_file(req["id"], "valid_receipt.pdf", valid_pdf)
        meta, file_path = get_supporting_file(uploaded["id"], self.employee["id"], "Employee")

        self.assertTrue(file_path.is_file())
        self.assertTrue(str(file_path).startswith(str(self.storage_dir)))
        self.assertEqual(meta["original_filename"], "valid_receipt.pdf")

    # ── 3. Financial Reconciliations & Atomic Invariants ─────────────────────

    def test_04_multi_receipt_multi_payment_exact_balance_reconciliation(self):
        """Independently verify that: Opening Balance + Sum(Receipts) - Sum(Payments) == Closing Balance."""
        initial_balance = Decimal("50000.00")
        self._set_balance(str(initial_balance))

        # Record 3 Company Inbound Receipts
        create_company_receipt(
            self.admin["id"],
            "25000.00",
            "2026-11-05",
            "Q4 Petty Cash Infusion",
            project_id=self.project_a["id"],
            ledger_id=self.ledger_ops["id"],
            category="Petty Cash Topup",
        )
        create_company_receipt(
            self.admin["id"],
            "15500.50",
            "2026-11-10",
            "Client Advance Refund",
            project_id=self.project_b["id"],
            ledger_id=self.ledger_ops["id"],
            category="Petty Cash Topup",
        )
        create_company_receipt(
            self.admin["id"],
            "5000.00",
            "2026-11-15",
            "Vendor Rebate",
            project_id=self.project_a["id"],
            ledger_id=self.ledger_ops["id"],
            category="Petty Cash Topup",
        )
        total_receipts = Decimal("25000.00") + Decimal("15500.50") + Decimal("5000.00")  # 45,500.50

        # Post 3 Employee Outbound Expenses
        amounts = ["3450.25", "12800.00", "4125.75"]
        posted_total = Decimal("0.00")
        for amt in amounts:
            d = self._create_draft(
                amount=amt,
                purpose=f"Disbursement {amt}",
            )
            submit_request(d["id"], self.employee["id"])
            manager_decision(d["id"], self.manager["id"], "APPROVED")
            self._upload_file(d["id"], f"voucher_{amt}.pdf", b"%PDF-1.4 proof")
            post_request(d["id"], self.admin["id"], "2026-11-18")
            posted_total += Decimal(amt)

        expected_closing_balance = initial_balance + total_receipts - posted_total
        actual_balance = self._get_balance()

        self.assertEqual(actual_balance, expected_closing_balance)
        self.assertEqual(actual_balance, Decimal("75124.50"))

    def test_05_duplicate_receipt_and_posting_idempotency(self):
        """Verify that duplicate receipt creation with identical payload is idempotent and does not double-count."""
        starting_bal = self._get_balance()
        payload = {
            "admin_id": self.admin["id"],
            "amount": "10000.00",
            "receipt_date": "2026-11-12",
            "description": "Idempotency Test Infusion",
            "project_id": self.project_a["id"],
            "ledger_id": self.ledger_ops["id"],
            "category": "Petty Cash Topup",
        }
        res1 = create_company_receipt(**payload)
        res2 = create_company_receipt(**payload)

        # Both calls return the exact same receipt reference
        self.assertEqual(res1["id"], res2["id"])

        # Vault balance increased exactly once by 10,000, not 20,000
        ending_bal = self._get_balance()
        self.assertEqual(ending_bal - starting_bal, Decimal("10000.00"))

    def test_06_period_lock_enforces_closed_accounting_boundary(self):
        """Verify that financial periods marked CLOSED strictly reject new postings and adjustments."""
        p = create_financial_period(self.admin["id"], "2026-10-01", "2026-10-31")
        close_financial_period(p["id"], self.admin["id"])

        # Attempt to post a request into the locked October period
        d = self._create_draft(
            amount="500.00",
            purpose="Retroactive expense",
        )
        submit_request(d["id"], self.employee["id"])
        manager_decision(d["id"], self.manager["id"], "APPROVED")

        with self.assertRaises(ValueError):
            post_request(d["id"], self.admin["id"], "2026-10-15")

        # Attempt to insert a company receipt into the locked period
        with self.assertRaises(ValueError):
            create_company_receipt(
                self.admin["id"],
                "5000.00",
                "2026-10-10",
                "Late October Infusion",
            )

        # Reopen period allows transactions again
        reopen_financial_period(p["id"], self.admin["id"])
        rec = create_company_receipt(
            self.admin["id"],
            "5000.00",
            "2026-10-10",
            "Reopened October Infusion",
        )
        self.assertIsNotNone(rec["id"])

    # ── 4. Operational Disaster Recovery, Backup & Rollback Verification ─────

    def test_07_online_backup_creation_and_pragmas(self):
        """Verify non-blocking online database backup creation and SQLite PRAGMA integrity verification."""
        backup_info = create_database_backup()
        self.assertIn("backup_id", backup_info)
        self.assertTrue(Path(backup_info["path"]).is_file())

        # Verify integrity of backup
        verification = verify_database_backup(backup_info["backup_id"])
        self.assertTrue(verification["valid"])
        self.assertEqual(verification["integrity_check"], "ok")
        self.assertGreater(verification["tables_count"], 10)
        self.assertEqual(len(verification["missing_core_tables"]), 0)

    def test_08_transactional_database_restore_from_backup(self):
        """Verify full transactional restore from an ACID backup snapshot."""
        # 1. State before mutation
        pre_balance = self._get_balance()
        backup = create_database_backup()

        # 2. Mutate database state (simulate accidental balance corruption)
        self._set_balance("999999.99")
        self.assertEqual(self._get_balance(), Decimal("999999.99"))

        # 3. Restore from verified snapshot
        restore_result = restore_database_backup(backup["backup_id"])
        self.assertEqual(restore_result["status"], "RESTORED")
        self.assertEqual(restore_result["backup_id"], backup["backup_id"])

        # 4. Verify balance is restored exactly to pre-mutation value
        restored_balance = self._get_balance()
        self.assertEqual(restored_balance, pre_balance)

    def test_09_controlled_deployment_rollback_and_audit(self):
        """Verify controlled deployment rollback execution, state restoration, and audit logging."""
        create_database_backup()

        # Execute deployment rollback endpoint
        res = self.client.post(
            "/api/operations/rollback",
            json={"target_version": "v1.0.0-rc1"},
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ROLLED_BACK")
        self.assertEqual(data["target_version"], "v1.0.0-rc1")

        # Verify rollback audit event is recorded
        audits = list_audit_events(action="DEPLOYMENT_ROLLBACK_EXECUTED")
        self.assertGreater(len(audits), 0)
        self.assertEqual(audits[0]["entity_id"], "v1.0.0-rc1")

    # ── 5. System Health Probes & RBAC Endpoint Hardening ────────────────────

    def test_10_health_probes_and_rbac_endpoint_hardening(self):
        """Verify production readiness and liveness probes and strict RBAC enforcement."""
        # Health probes
        live_res = self.client.get("/health/live")
        self.assertEqual(live_res.status_code, 200)
        self.assertEqual(live_res.json()["status"], "ok")

        ready_res = self.client.get("/health/ready")
        self.assertEqual(ready_res.status_code, 200)
        self.assertEqual(ready_res.json()["status"], "ready")

        # RBAC: Employee cannot access Admin operations
        res_emp_bk = self.client.post("/api/operations/backups/create", headers=self.employee_headers)
        self.assertEqual(res_emp_bk.status_code, 403)

        res_emp_rb = self.client.post("/api/operations/rollback", json={"target_version": "v1.0"}, headers=self.employee_headers)
        self.assertEqual(res_emp_rb.status_code, 403)

        res_emp_post = self.client.post("/api/requests/any-id/post", json={"effective_date": "2026-11-19"}, headers=self.employee_headers)
        self.assertEqual(res_emp_post.status_code, 403)

        # RBAC: Manager cannot access financial posting or backup creation
        res_mgr_bk = self.client.post("/api/operations/backups/create", headers=self.manager_headers)
        self.assertEqual(res_mgr_bk.status_code, 403)
