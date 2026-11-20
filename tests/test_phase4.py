import tempfile
import unittest
from pathlib import Path

from backend import database
from backend.request_service import (
    create_draft,
    get_request,
    manager_decision,
    submit_request,
    update_draft,
)
from backend.user_service import (
    create_assignment,
    create_bootstrap_admin,
    provision_user,
    review_assignment,
)
from backend.domain_repository import create_master_record


class Phase4Tests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "requests.sqlite")
        database.DATABASE_URL = None
        database.init_db()

        admin = create_bootstrap_admin("admin", "admin@example.com", "a-secure-password")
        manager, _ = provision_user("manager", "manager@example.com", "Manager", admin["id"])
        employee, _ = provision_user("employee", "employee@example.com", "Employee", admin["id"])
        assignment = create_assignment(manager["id"], employee["id"], admin["id"])
        review_assignment(assignment["id"], manager["id"], "APPROVED")
        self.admin = admin
        self.manager = manager
        self.employee = employee
        self.project = create_master_record("projects", "Office")
        self.ledger = create_master_record("ledgers", "Petty Cash")

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        self.temp_dir.cleanup()

    def create_request(self):
        return create_draft(
            self.employee["id"],
            self.project["id"],
            self.ledger["id"],
            "Travel",
            "2026-11-17",
            "300.00",
            "Travel to client office",
            "Taxi and meals",
            self.manager["id"],
        )

    def test_draft_submission_approval_and_history(self):
        request = self.create_request()
        self.assertEqual(request["status"], "DRAFT")
        submitted = submit_request(request["id"], self.employee["id"])
        self.assertEqual(submitted["status"], "SUBMITTED")
        approved = manager_decision(request["id"], self.manager["id"], "APPROVED", None)
        self.assertEqual(approved["status"], "APPROVED")
        self.assertEqual(
            [item["to_status"] for item in get_request(request["id"])["history"]],
            ["DRAFT", "SUBMITTED", "APPROVED"],
        )

    def test_request_changes_returns_editable_draft(self):
        request = self.create_request()
        submit_request(request["id"], self.employee["id"])
        changed = manager_decision(
            request["id"],
            self.manager["id"],
            "DRAFT",
            "Please clarify the business purpose.",
        )
        self.assertEqual(changed["status"], "DRAFT")
        edited = update_draft(
            request["id"],
            self.employee["id"],
            {"purpose": "Client meeting and approved travel"},
        )
        self.assertEqual(edited["purpose"], "Client meeting and approved travel")

    def test_rejection_requires_reason_and_ends_workflow(self):
        request = self.create_request()
        submit_request(request["id"], self.employee["id"])
        with self.assertRaises(ValueError):
            manager_decision(request["id"], self.manager["id"], "REJECTED", None)
        rejected = manager_decision(
            request["id"],
            self.manager["id"],
            "REJECTED",
            "Expense is outside the approved policy.",
        )
        self.assertEqual(rejected["status"], "REJECTED")

    def test_requester_cannot_self_approve_and_unassigned_manager_is_rejected(self):
        with self.assertRaises(ValueError):
            create_draft(
                self.employee["id"],
                self.project["id"],
                self.ledger["id"],
                "Travel",
                "2026-11-17",
                100,
                "Invalid self approval",
                None,
                self.employee["id"],
            )

        other_manager, _ = provision_user(
            "other-manager", "other@example.com", "Manager", self.admin["id"]
        )
        with self.assertRaises(ValueError):
            create_draft(
                self.employee["id"],
                self.project["id"],
                self.ledger["id"],
                "Travel",
                "2026-11-17",
                100,
                "Unassigned manager",
                None,
                other_manager["id"],
            )

    def test_only_drafts_can_be_edited(self):
        request = self.create_request()
        submit_request(request["id"], self.employee["id"])
        with self.assertRaises(ValueError):
            update_draft(
                request["id"],
                self.employee["id"],
                {"purpose": "Should not edit submitted request"},
            )


if __name__ == "__main__":
    unittest.main()
