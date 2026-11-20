import tempfile
import unittest
from pathlib import Path

from backend import database
from backend.receipt_service import create_company_receipt, list_company_receipts
from backend.user_service import create_bootstrap_admin, provision_user
from backend.domain_repository import create_master_record


class Phase6Tests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "phase6.sqlite")
        database.DATABASE_URL = None
        database.init_db()
        self.admin = create_bootstrap_admin(
            "admin", "admin@example.com", "a-secure-password"
        )
        self.manager, _ = provision_user(
            "manager", "manager@example.com", "Manager", self.admin["id"]
        )
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
                ("4700.00",),
            )
            connection.commit()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        self.temp_dir.cleanup()

    def test_receipt_increases_balance_once_and_is_audited(self):
        receipt = create_company_receipt(
            self.admin["id"],
            150,
            "2026-11-18",
            "Petty cash replenishment",
            self.ledger["id"],
            "Cash replenishment",
            self.project["id"],
        )
        self.assertFalse(receipt["duplicate"])

        duplicate = create_company_receipt(
            self.admin["id"],
            "150.00",
            "2026-11-18",
            "Petty cash replenishment",
            self.ledger["id"],
            "Cash replenishment",
            self.project["id"],
        )
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(receipt["id"], duplicate["id"])

        with database.get_connection() as connection:
            balance = connection.execute(
                """
                SELECT current_balance FROM cash_account_balances
                WHERE cash_account_id='system-main-cash'
                """
            ).fetchone()[0]
            receipt_count = connection.execute(
                "SELECT COUNT(*) FROM company_receipts"
            ).fetchone()[0]
            entry_count = connection.execute(
                "SELECT COUNT(*) FROM ledger_entries WHERE company_receipt_id=?",
                (receipt["id"],),
            ).fetchone()[0]
            audit_count = connection.execute(
                """
                SELECT COUNT(*) FROM audit_events
                WHERE action='COMPANY_CASH_RECEIPT_POSTED'
                  AND entity_id=?
                """,
                (receipt["id"],),
            ).fetchone()[0]

        self.assertEqual(float(balance), 4850.0)
        self.assertEqual(receipt_count, 1)
        self.assertEqual(entry_count, 1)
        self.assertEqual(audit_count, 1)

    def test_invalid_amount_and_date_are_rejected(self):
        with self.assertRaises(ValueError):
            create_company_receipt(
                self.admin["id"], 0, "2026-11-18", "Top up",
                self.ledger["id"], "Cash replenishment", self.project["id"]
            )
        with self.assertRaises(ValueError):
            create_company_receipt(
                self.admin["id"], 100, "18-11-2026", "Top up",
                self.ledger["id"], "Cash replenishment", self.project["id"]
            )

    def test_repeated_payload_is_a_single_receipt_and_has_generated_reference(self):
        first = create_company_receipt(
            self.admin["id"], 100, "2026-11-18", "Top up",
            self.ledger["id"], "Cash replenishment", self.project["id"]
        )
        second = create_company_receipt(
            self.admin["id"], "100.00", "2026-11-18", "Top up",
            self.ledger["id"], "Cash replenishment", self.project["id"]
        )
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(first["receipt_reference"].startswith("RCPT-"))

    def test_only_admin_can_create_receipt(self):
        with self.assertRaises(PermissionError):
            create_company_receipt(
                self.manager["id"],
                100,
                "2026-11-18",
                "Unauthorized top up",
                self.ledger["id"],
                "Cash replenishment",
                self.project["id"],
            )
        self.assertEqual(list_company_receipts(self.admin["id"]), [])


if __name__ == "__main__":
    unittest.main()
