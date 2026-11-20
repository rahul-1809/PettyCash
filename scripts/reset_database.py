"""Database reset utility for PettyCash Pro.

Safely clears all demo/transactional data, users, and audit records,
leaving the schema, system roles, and baseline categories ready for production bootstrap.
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to Python module path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import database


TABLES_TO_CLEAR = [
    "supporting_files",
    "request_status_history",
    "petty_cash_requests",
    "company_receipts",
    "financial_periods",
    "vault_adjustments",
    "review_assignments",
    "user_sessions",
    "onboarding_tokens",
    "notification_preferences",
    "notifications",
    "audit_events",
    "users",
    "sessions",
]


def reset_database(force: bool = False) -> None:
    db_engine = "Supabase PostgreSQL" if database.DATABASE_URL else "Local SQLite"
    print(f"Target Database: {db_engine}")
    if database.DATABASE_URL:
        print(f"Database URL: {database.DATABASE_URL[:40]}...")

    if not force:
        print("\nWARNING: This will permanently delete all users, requests, receipts, and audit events.")
        confirm = input("Type 'RESET' to confirm: ").strip()
        if confirm != "RESET":
            print("Aborted. No data was modified.")
            return

    with database.get_connection() as conn:
        for table in TABLES_TO_CLEAR:
            try:
                if database.DATABASE_URL:
                    conn.execute(f"TRUNCATE TABLE {table} CASCADE")
                else:
                    conn.execute(f"DELETE FROM {table}")
                print(f"  ✓ Cleared table: {table}")
            except Exception as exc:
                # Some tables may not exist yet or error if already empty
                print(f"  - Skipped/Empty table {table}: {exc}")

        # Ensure base system roles and categories remain populated
        database.seed_system_roles()
        database._seed_project_categories()
        conn.commit()

    print("\nDatabase reset complete!")
    print("The system is now in a pristine state with 0 users.")
    print("Open the web app or run 'python scripts/create_admin.py' to initialize the first real administrator.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset PettyCash Pro database for production.")
    parser.add_argument("--force", action="store_true", help="Bypass confirmation prompt")
    args = parser.parse_args()
    reset_database(force=args.force)
