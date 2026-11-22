import io
import os
import tempfile
import unittest
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
from backend.audit_service import list_audit_events


class Phase10Tests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "phase10.sqlite")
        database.DATABASE_URL = None
        database.init_db()

        # Users setup
        self.admin = create_bootstrap_admin("admin", "admin@example.com", "a-secure-password")
        self.admin_token = create_auth_session(self.admin["id"])

        self.manager, _ = provision_user("manager", "manager@example.com", "Manager", self.admin["id"])
        self.manager_token = create_auth_session(self.manager["id"])

        self.employee, _ = provision_user("employee", "employee@example.com", "Employee", self.admin["id"])
        self.employee_token = create_auth_session(self.employee["id"])

        # Master data setup
        self.project = create_master_record("projects", "Core Operations")
        self.ledger = create_master_record("ledgers", "Office Administration")

        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url

    def test_01_frontend_production_build_and_serving(self):
        """Acceptance Criteria: Frontend production build assets exist and are served cleanly."""
        dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
        self.assertTrue(dist_dir.is_dir(), "frontend/dist directory must exist.")
        self.assertTrue((dist_dir / "index.html").is_file(), "index.html must exist in dist.")
        self.assertTrue((dist_dir / "assets").is_dir(), "assets/ directory must exist in dist.")

        # Test root endpoint returns the frontend shell
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("<!doctype html>", res.text.lower())
        self.assertIn("assets/index-", res.text)

    def test_02_rbac_unauthorized_action_rejection(self):
        """Acceptance Criteria: Unauthorized actions are rejected by backend regardless of UI state."""
        # 1. Employee cannot list or provision users
        res_user_list = self.client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {self.employee_token}"},
        )
        self.assertEqual(res_user_list.status_code, 403)

        res_provision = self.client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {self.employee_token}"},
            json={"username": "hacker", "email": "hack@example.com", "role": "Admin"},
        )
        self.assertEqual(res_provision.status_code, 403)

        # 2. Employee cannot configure cash vault balance
        res_vault = self.client.put(
            "/api/cash-balance",
            headers={"Authorization": f"Bearer {self.employee_token}"},
            json={"opening_balance": 1000000.0},
        )
        self.assertEqual(res_vault.status_code, 403)

        # 3. Employee cannot post to ledger
        res_post = self.client.post(
            "/api/requests/req-123/post",
            headers={"Authorization": f"Bearer {self.employee_token}"},
            json={"effective_date": "2026-11-18"},
        )
        self.assertEqual(res_post.status_code, 403)

        # 4. Manager cannot trigger database backups
        res_backup = self.client.post(
            "/api/operations/backups/create",
            headers={"Authorization": f"Bearer {self.manager_token}"},
        )
        self.assertEqual(res_backup.status_code, 403)

    def test_03_end_to_end_role_based_workflow(self):
        """Acceptance Criteria: Employee creation, Manager approval, and Admin posting can be completed through API/UI."""
        # Step 1: Admin configures cash vault opening balance to 50,000
        res_bal = self.client.put(
            "/api/cash-balance",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"opening_balance": 50000.00},
        )
        self.assertEqual(res_bal.status_code, 200)

        # Step 2: Admin assigns employee to manager
        res_assign = self.client.post(
            "/api/assignments",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"manager_id": self.manager["id"], "employee_id": self.employee["id"]},
        )
        self.assertEqual(res_assign.status_code, 200)
        assignment_id = res_assign.json()["id"]

        # Step 3: Manager reviews and approves the assignment
        res_review_assign = self.client.post(
            f"/api/assignments/{assignment_id}/review",
            headers={"Authorization": f"Bearer {self.manager_token}"},
            json={"decision": "APPROVED", "reason": "Assigned to my unit"},
        )
        self.assertEqual(res_review_assign.status_code, 200)
        self.assertEqual(res_review_assign.json()["status"], "APPROVED")

        # Step 4: Employee creates a draft request for ₹2,450.00
        res_draft = self.client.post(
            "/api/requests",
            headers={"Authorization": f"Bearer {self.employee_token}"},
            json={
                "project_id": self.project["id"],
                "ledger_id": self.ledger["id"],
                "category": "Office Supplies",
                "request_date": "2026-11-18",
                "amount": 2450.00,
                "purpose": "Printer ink and paper reams",
                "notes": "Purchased for admin printer",
                "approving_manager_id": self.manager["id"],
            },
        )
        self.assertEqual(res_draft.status_code, 200)
        request_id = res_draft.json()["id"]
        self.assertEqual(res_draft.json()["status"], "DRAFT")

        # Step 5: Employee submits the draft for manager approval
        res_submit = self.client.post(
            f"/api/requests/{request_id}/submit",
            headers={"Authorization": f"Bearer {self.employee_token}"},
        )
        self.assertEqual(res_submit.status_code, 200)
        self.assertEqual(res_submit.json()["status"], "SUBMITTED")

        # Step 6: Manager approves the submitted request
        res_approve = self.client.post(
            f"/api/requests/{request_id}/approve",
            headers={"Authorization": f"Bearer {self.manager_token}"},
        )
        self.assertEqual(res_approve.status_code, 200)
        self.assertEqual(res_approve.json()["status"], "APPROVED")

        # Step 7: Employee uploads supporting receipt voucher file (PDF) on approved request
        pdf_bytes = b"%PDF-1.4 sample receipt voucher"
        res_file = self.client.post(
            f"/api/requests/{request_id}/supporting-files",
            headers={"Authorization": f"Bearer {self.employee_token}"},
            files={"file": ("stationery_invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        self.assertEqual(res_file.status_code, 200)
        self.assertEqual(res_file.json()["original_filename"], "stationery_invoice.pdf")

        # Step 8: Admin posts the approved request to canonical ledger with effective date
        res_post = self.client.post(
            f"/api/requests/{request_id}/post",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"effective_date": "2026-11-18"},
        )
        self.assertEqual(res_post.status_code, 200)
        posted_data = res_post.json()
        self.assertEqual(posted_data["status"], "POSTED")

        # Step 9: Reconcile financial vault balance (50,000 - 2,450 = 47,550)
        res_final_bal = self.client.get(
            "/api/cash-balance",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(res_final_bal.status_code, 200)
        self.assertAlmostEqual(float(res_final_bal.json()["current_balance"]), 47550.00, places=2)

        # Step 10: Verify audit trail contains complete provenance
        audit_events = list_audit_events(entity_id=request_id)
        action_names = [e["action"] for e in audit_events]
        self.assertIn("PETTY_CASH_REQUEST_SUBMITTED", action_names)
        self.assertIn("PETTY_CASH_REQUEST_APPROVED", action_names)
        self.assertIn("PETTY_CASH_REQUEST_POSTED", action_names)

    def test_04_self_approval_prevention(self):
        """Acceptance Criteria: Self-approval is strictly prevented by business logic."""
        # Provision a manager who also attempts to submit and approve own request
        res_self_draft = self.client.post(
            "/api/requests",
            headers={"Authorization": f"Bearer {self.employee_token}"},
            json={
                "project_id": self.project["id"],
                "ledger_id": self.ledger["id"],
                "category": "Travel",
                "request_date": "2026-11-18",
                "amount": 500.00,
                "purpose": "Self-approval test",
                "approving_manager_id": self.employee["id"],  # Same user!
            },
        )
        self.assertEqual(res_self_draft.status_code, 400)
        self.assertIn("cannot approve their own request", res_self_draft.json()["detail"].lower())

    def test_05_compatibility_spreadsheet_workflows(self):
        """Acceptance Criteria: Existing import and compatibility workflows remain available and functional."""
        # Test recalculation endpoint
        sample_txs = [
            {"date": "2026-11-01", "ledger": "Petty Cash", "memo": "Office Tea", "receipt": 0, "payment": 150, "balance": 4850, "project": "General"},
            {"date": "2026-11-02", "ledger": "Petty Cash", "memo": "Courier", "receipt": 0, "payment": 200, "balance": 4650, "project": "General"},
        ]
        res_recalc = self.client.post(
            "/api/recalculate",
            json={
                "opening_balance": 5000.0,
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
                "transactions": sample_txs,
            },
        )
        self.assertEqual(res_recalc.status_code, 200)
        recalc_data = res_recalc.json()
        self.assertEqual(recalc_data["total_payments"], 350.0)
        self.assertEqual(recalc_data["closing_balance"], 4650.0)

        # Test session save and retrieve
        res_save_session = self.client.post(
            "/api/sessions",
            json={
                "name": "Phase 10 Migration Session",
                "opening_balance": 5000.0,
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
                "transactions": sample_txs,
            },
        )
        self.assertEqual(res_save_session.status_code, 200)
        session_id = res_save_session.json()["id"]

        res_get_session = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(res_get_session.status_code, 200)
        self.assertEqual(res_get_session.json()["name"], "Phase 10 Migration Session")

    def test_06_notifications_read_unread_endpoints(self):
        """Test marking notifications as read, unread, and mark all read."""
        from backend.notification_service import create_notification, list_notifications

        notif1 = create_notification(self.employee["id"], "TEST_EVENT_1", "Test 1", "Message 1")
        notif2 = create_notification(self.employee["id"], "TEST_EVENT_2", "Test 2", "Message 2")

        headers = {"Authorization": f"Bearer {self.employee_token}"}

        # Verify unread list has 2
        res = self.client.get("/api/notifications?unread_only=true", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 2)

        # Mark notif1 as read
        res_read = self.client.post(f"/api/notifications/{notif1['id']}/read", headers=headers)
        self.assertEqual(res_read.status_code, 200)
        self.assertTrue(res_read.json()["read"])

        # Verify unread list now has 1
        res = self.client.get("/api/notifications?unread_only=true", headers=headers)
        self.assertEqual(len(res.json()), 1)

        # Mark notif1 as unread
        res_unread = self.client.post(f"/api/notifications/{notif1['id']}/unread", headers=headers)
        self.assertEqual(res_unread.status_code, 200)
        self.assertFalse(res_unread.json()["read"])

        # Verify unread list has 2 again
        res = self.client.get("/api/notifications?unread_only=true", headers=headers)
        self.assertEqual(len(res.json()), 2)

        # Mark all as read
        res_all = self.client.post("/api/notifications/mark-all-read", headers=headers)
        self.assertEqual(res_all.status_code, 200)
        self.assertEqual(res_all.json()["marked_read"], 2)

        # Verify unread list is now 0
        res = self.client.get("/api/notifications?unread_only=true", headers=headers)
        self.assertEqual(len(res.json()), 0)

    def test_07_manager_assignments_filtered_and_emails(self):
        """Test manager assignment listings return emails and correct status separation."""
        assignment = create_assignment(self.manager["id"], self.employee["id"], self.admin["id"])
        headers = {"Authorization": f"Bearer {self.manager_token}"}

        res = self.client.get("/api/assignments", headers=headers)
        self.assertEqual(res.status_code, 200)
        assignments = res.json()
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]["employee_email"], "employee@example.com")
        self.assertEqual(assignments[0]["status"], "PENDING")

        # Approve assignment
        review_res = self.client.post(
            f"/api/assignments/{assignment['id']}/review",
            headers=headers,
            json={"decision": "APPROVED", "reason": "Approved team member"}
        )
        self.assertEqual(review_res.status_code, 200)
        self.assertEqual(review_res.json()["status"], "APPROVED")

        # Re-fetch assignments: status is now APPROVED
        res = self.client.get("/api/assignments", headers=headers)
        self.assertEqual(res.status_code, 200)
        updated = res.json()
        pending = [a for a in updated if a["status"] == "PENDING"]
        approved = [a for a in updated if a["status"] == "APPROVED"]
        self.assertEqual(len(pending), 0)
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["employee_username"], "employee")

    def test_08_spreadsheet_zip_bundle_and_session_optimization(self):
        """Test spreadsheet session ZIP bundle export and payload optimization."""
        import zipfile
        import io

        # 1. Create a session with sample transactions including base64 supportings
        sample_txs = [
            {
                "id": "tx-zip-1",
                "date": "2026-10-05",
                "ledger": "Office Supplies",
                "memo": "Printer ink & stationery",
                "receipt": 0,
                "payment": 1500.0,
                "balance": -1500.0,
                "project": "HQ Admin",
                "status": "APPROVED",
                "supportings": [
                    {
                        "name": "receipt_1.txt",
                        "data": "VGhpcyBpcyBhIHRlc3QgcmVjZWlwdCBmaWxlLg==", # "This is a test receipt file."
                        "type": "text/plain",
                    }
                ],
            }
        ]
        create_res = self.client.post(
            "/api/sessions",
            json={
                "name": "Audit Ready Oct 2026",
                "opening_balance": 5000.0,
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
                "transactions": sample_txs,
                "source_excel_base64": "U0FNUExFX0VYQ0VMX0RBVEE=",
                "source_excel_filename": "source.xlsx",
            },
        )
        self.assertEqual(create_res.status_code, 200)
        session_id = create_res.json()["id"]

        # 2. Test lightweight get session (excludes huge source_excel_base64)
        get_res = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertNotIn("source_excel_base64", get_res.json())

        # Include raw includes it
        get_raw_res = self.client.get(f"/api/sessions/{session_id}?include_raw=true")
        self.assertEqual(get_raw_res.status_code, 200)
        self.assertEqual(get_raw_res.json().get("source_excel_base64"), "U0FNUExFX0VYQ0VMX0RBVEE=")

        # 3. Test GET /api/sessions/{session_id}/zip
        zip_res = self.client.get(f"/api/sessions/{session_id}/zip")
        self.assertEqual(zip_res.status_code, 200)
        self.assertEqual(zip_res.headers.get("content-type"), "application/zip")
        self.assertIn("Audit_Ready_Oct_2026_Bundle.zip", zip_res.headers.get("content-disposition", ""))

        zf = zipfile.ZipFile(io.BytesIO(zip_res.content))
        names = zf.namelist()
        self.assertTrue(any(n.endswith(".xlsx") for n in names))
        self.assertIn("evidence_viewer.html", names)
        self.assertTrue(any(n.startswith("supportings/") for n in names))

        # Check evidence viewer content
        viewer_html = zf.read("evidence_viewer.html").decode("utf-8")
        self.assertIn("Audit Ready Oct 2026", viewer_html)
        self.assertIn("Printer ink &amp; stationery", viewer_html)
        self.assertIn("receipt_1.txt", viewer_html)

        # 4. Test POST /api/export-zip for on-the-fly export
        export_zip_res = self.client.post(
            "/api/export-zip",
            json={
                "name": "Live State Bundle",
                "opening_balance": 1000.0,
                "start_date": "2026-11-01",
                "end_date": "2026-11-15",
                "transactions": sample_txs,
            },
        )
        self.assertEqual(export_zip_res.status_code, 200)
        self.assertEqual(export_zip_res.headers.get("content-type"), "application/zip")
        zf2 = zipfile.ZipFile(io.BytesIO(export_zip_res.content))
        self.assertIn("evidence_viewer.html", zf2.namelist())

    def test_09_email_queue_and_test_email_endpoint(self):
        """Test serialized email queue enqueueing and test-email endpoint."""
        from unittest.mock import patch
        from backend.notification_service import enqueue_email, send_test_email

        # 1. Test enqueue_email
        enqueue_email("test@example.com", "Subject", "Body")

        # 2. Test send_test_email mocking send_email
        with patch("backend.notification_service.send_email") as mock_send:
            send_test_email("user@example.com", "Test User")
            self.assertTrue(mock_send.called)
            call_kwargs = mock_send.call_args[1]
            self.assertEqual(call_kwargs["recipient"], "user@example.com")
            self.assertIn("PettyCash Pro - Notification Delivery Test", call_kwargs["subject"])

        # 3. Test POST /api/notifications/test-email endpoint
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        with patch("backend.main.send_test_email") as mock_endpoint_send:
            res = self.client.post("/api/notifications/test-email", headers=headers)
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()["success"])
            self.assertEqual(res.json()["recipient"], self.admin["email"])


if __name__ == "__main__":
    unittest.main()
