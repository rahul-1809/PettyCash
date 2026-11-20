import tempfile
import unittest
from pathlib import Path

from backend import database
from backend.domain_repository import create_master_record
from backend.posting_service import post_request
from backend.request_service import create_draft, manager_decision, submit_request
from backend.supporting_service import upload_supporting_file
from backend.user_service import (
    create_assignment,
    create_bootstrap_admin,
    provision_user,
    review_assignment,
)


class Phase5Tests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "phase5.sqlite")
        database.DATABASE_URL = None
        database.init_db()

        self.admin = create_bootstrap_admin("admin", "admin@example.com", "a-secure-password")
        self.manager, _ = provision_user("manager", "manager@example.com", "Manager", self.admin["id"])
        self.employee, _ = provision_user("employee", "employee@example.com", "Employee", self.admin["id"])
        assignment = create_assignment(self.manager["id"], self.employee["id"], self.admin["id"])
        review_assignment(assignment["id"], self.manager["id"], "APPROVED")
        self.project = create_master_record("projects", "Office")
        self.ledger = create_master_record("ledgers", "Petty Cash")
        marker = database._placeholder()
        with database.get_connection() as connection:
            connection.execute(
                f"""
                UPDATE cash_account_balances
                SET current_balance={marker}
                WHERE cash_account_id='system-main-cash'
                """,
                ("500.00",),
            )
            connection.commit()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        self.temp_dir.cleanup()

    def create_approved_request(self, amount="300.00"):
        request = create_draft(
            self.employee["id"],
            self.project["id"],
            self.ledger["id"],
            "Travel",
            "2026-11-17",
            amount,
            "Travel to client office",
            None,
            self.manager["id"],
        )
        submit_request(request["id"], self.employee["id"])
        return manager_decision(request["id"], self.manager["id"], "APPROVED", None)

    def test_upload_requires_approval_and_verifies_content(self):
        request = create_draft(
            self.employee["id"],
            self.project["id"],
            self.ledger["id"],
            "Travel",
            "2026-11-17",
            "50.00",
            "Taxi",
            None,
            self.manager["id"],
        )
        with self.assertRaises(ValueError):
            upload_supporting_file(
                request["id"], self.employee["id"], "receipt.pdf", "application/pdf", b"%PDF-1.7"
            )
        approved = self.create_approved_request("50.00")
        with self.assertRaises(ValueError):
            upload_supporting_file(
                approved["id"], self.employee["id"], "receipt.pdf", "application/pdf", b"not a pdf"
            )
        uploaded = upload_supporting_file(
            approved["id"],
            self.employee["id"],
            "receipt.pdf",
            "application/pdf",
            b"%PDF-1.7 receipt",
        )
        self.assertEqual(uploaded["original_filename"], "receipt.pdf")

    def test_posting_atomically_deducts_balance_and_is_not_repeatable(self):
        request = self.create_approved_request()
        upload_supporting_file(
            request["id"],
            self.employee["id"],
            "receipt.png",
            "image/png",
            b"\x89PNG\r\n\x1a\nreceipt",
        )
        result = post_request(request["id"], self.admin["id"], "2026-11-18")
        self.assertEqual(result["status"], "POSTED")
        with database.get_connection() as connection:
            balance = connection.execute(
                "SELECT current_balance FROM cash_account_balances WHERE cash_account_id='system-main-cash'"
            ).fetchone()[0]
            entry_count = connection.execute(
                "SELECT COUNT(*) FROM ledger_entries WHERE request_id=?",
                (request["id"],),
            ).fetchone()[0]
        self.assertEqual(float(balance), 200.0)
        self.assertEqual(entry_count, 1)
        with self.assertRaises(ValueError):
            post_request(request["id"], self.admin["id"], "2026-11-18")

    def test_insufficient_balance_rolls_back(self):
        request = self.create_approved_request("600.00")
        upload_supporting_file(
            request["id"],
            self.employee["id"],
            "receipt.jpg",
            "image/jpeg",
            b"\xff\xd8\xff receipt",
        )
        with self.assertRaises(ValueError):
            post_request(request["id"], self.admin["id"], "2026-11-18")
        with database.get_connection() as connection:
            balance = connection.execute(
                "SELECT current_balance FROM cash_account_balances WHERE cash_account_id='system-main-cash'"
            ).fetchone()[0]
        self.assertEqual(float(balance), 500.0)


if __name__ == "__main__":
    unittest.main()
