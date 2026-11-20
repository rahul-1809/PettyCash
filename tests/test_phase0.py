import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from backend import database
from backend.excel_service import (
    generate_styled_excel,
    parse_petty_cash_file,
    recalculate_summary,
)
from backend.legacy_migration import export_legacy_sessions


class Phase0Tests(unittest.TestCase):
    def test_recalculate_summary_preserves_balance_invariant(self):
        result = recalculate_summary(
            opening_balance=1000,
            start_date="2026-01-01",
            end_date="2026-01-02",
            transactions=[
                {"date": "2026-01-01", "receipt": 250, "payment": 0, "project": "Office"},
                {"date": "2026-01-02", "receipt": 0, "payment": 125.50, "project": "Office"},
            ],
        )

        self.assertEqual(result["total_receipts"], 250)
        self.assertEqual(result["total_payments"], 125.50)
        self.assertEqual(result["closing_balance"], 1124.50)
        self.assertEqual(result["transactions"][-1]["balance"], 1124.50)

    def test_excel_import_retains_transaction_values(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Petty Cash Sheet"
        sheet.append(
            [
                "Date",
                "Ledger",
                "Memo / Description",
                "Receipt",
                "Payment",
                "Outstanding Balance",
                "Approved",
                "Requested By",
                "Category",
                "Project",
            ]
        )
        sheet.append(
            [
                "2026-01-01",
                "Petty Cash",
                "Opening receipt",
                500,
                0,
                500,
                "Admin",
                "Employee",
                "Cash",
                "Office",
            ]
        )

        from io import BytesIO

        stream = BytesIO()
        workbook.save(stream)
        data = parse_petty_cash_file(stream.getvalue())

        self.assertEqual(len(data["transactions"]), 1)
        self.assertEqual(data["transactions"][0]["receipt"], 500)
        self.assertEqual(data["transactions"][0]["project"], "Office")

    def test_sqlite_session_round_trip_uses_isolated_test_database(self):
        original_db_path = database.DB_PATH
        original_database_url = database.DATABASE_URL
        with tempfile.TemporaryDirectory() as temp_dir:
            database.DB_PATH = str(Path(temp_dir) / "test.sqlite")
            database.DATABASE_URL = None
            try:
                database.init_db()
                created = database.create_session(
                    name="Test session",
                    opening_balance=100,
                    start_date="2026-01-01",
                    end_date="2026-01-01",
                    transactions=[],
                    summary={"closing_balance": 100},
                )
                loaded = database.get_session(created["id"])
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded["name"], "Test session")
                self.assertEqual(database.list_sessions()[0]["tx_count"], 0)
            finally:
                database.DB_PATH = original_db_path
                database.DATABASE_URL = original_database_url

    def test_database_initialization_is_idempotent(self):
        original_db_path = database.DB_PATH
        original_database_url = database.DATABASE_URL
        with tempfile.TemporaryDirectory() as temp_dir:
            database.DB_PATH = str(Path(temp_dir) / "test.sqlite")
            database.DATABASE_URL = None
            try:
                database.init_db()
                database.init_db()
                with database.get_connection() as connection:
                    migration_count = connection.execute(
                        "SELECT COUNT(*) FROM schema_migrations"
                    ).fetchone()[0]
                self.assertGreaterEqual(migration_count, 4)
            finally:
                database.DB_PATH = original_db_path
                database.DATABASE_URL = original_database_url

    def test_excel_export_contains_legacy_workbook_sheets(self):
        stream = generate_styled_excel(
            opening_balance=100,
            start_date="2026-01-01",
            end_date="2026-01-01",
            transactions=[
                {
                    "date": "2026-01-01",
                    "ledger": "Petty Cash",
                    "memo": "Test payment",
                    "payment": 10,
                    "project": "Office",
                }
            ],
        )
        from openpyxl import load_workbook

        workbook = load_workbook(stream, data_only=False)
        self.assertIn("Petty Cash Sheet", workbook.sheetnames)
        self.assertIn("Petty Cash Summary ", workbook.sheetnames)

    def test_legacy_export_is_read_only_and_round_trips(self):
        sessions = [{"id": "session-1", "name": "Legacy"}]
        full_session = {
            "id": "session-1",
            "name": "Legacy",
            "data": {"transactions": [{"id": "tx-1", "payment": 10}]},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "legacy.json"
            count = export_legacy_sessions(
                output,
                lambda: sessions,
                lambda session_id: full_session if session_id == "session-1" else None,
            )
            self.assertEqual(count, 1)
            self.assertIn("pettycash-legacy-session-v1", output.read_text())
            self.assertEqual(sessions, [{"id": "session-1", "name": "Legacy"}])


if __name__ == "__main__":
    unittest.main()

