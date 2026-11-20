import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend import database
from backend.domain_repository import (
    create_cash_account,
    create_master_record,
    create_role,
    create_user,
    get_cash_account_balance,
    list_cash_accounts,
    list_master_records,
    set_master_record_active,
)


class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "phase1.sqlite")
        database.DATABASE_URL = None
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        self.temp_dir.cleanup()

    def test_domain_migrations_create_normalized_tables(self):
        expected_tables = {
            "roles",
            "users",
            "projects",
            "ledgers",
            "categories",
            "cash_accounts",
            "cash_account_balances",
            "petty_cash_requests",
            "request_status_history",
            "supporting_files",
            "ledger_entries",
            "company_receipts",
            "notifications",
            "notification_preferences",
            "audit_events",
            "financial_periods",
            "legacy_ledger_sessions",
        }
        with database.get_connection() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {row["name"] for row in rows}
            migration_count = connection.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0]

        self.assertTrue(expected_tables.issubset(tables))
        self.assertGreaterEqual(migration_count, 4)

    def test_repository_persists_master_data_and_balance(self):
        role = create_role("Admin")
        user = create_user("admin", "ADMIN@example.com", role["id"])
        project = create_master_record("projects", "Office")
        ledger = create_master_record("ledgers", "Petty Cash")
        category = create_master_record("categories", "Travel")
        account = create_cash_account("Main Cash", "5000.00", "100.00")

        self.assertEqual(user["email"], "admin@example.com")
        self.assertTrue(project["id"])
        self.assertTrue(ledger["id"])
        self.assertTrue(category["id"])
        self.assertEqual(
            get_cash_account_balance(account["id"])["current_balance"],
            5000,
        )
        self.assertEqual(list_cash_accounts()[0]["name"], "Main Cash")
        self.assertEqual(list_master_records("projects")[0]["name"], "Office")

        self.assertTrue(set_master_record_active("projects", project["id"], False))
        self.assertEqual(list_master_records("projects")[0]["is_active"], 0)

    def test_constraints_reject_invalid_money_and_missing_foreign_keys(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with database.get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO cash_accounts
                        (id, name, opening_balance, minimum_balance, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("account-1", "Invalid", 0, -1, "now", "now"),
                )

        with self.assertRaises(sqlite3.IntegrityError):
            with database.get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO users
                        (id, username, email, role_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("user-1", "user", "user@example.com", "missing-role", "now", "now"),
                )

    def test_account_creation_rolls_back_if_balance_insert_fails(self):
        with self.assertRaises(sqlite3.IntegrityError):
            create_cash_account("Broken", "100.00", "-1.00")

        with database.get_connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM cash_accounts WHERE name = ?",
                ("Broken",),
            ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
