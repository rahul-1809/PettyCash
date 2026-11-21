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
from backend.auth_service import clear_auth_cache


TARGET_TABLES = [
    "supporting_files",
    "request_status_history",
    "petty_cash_requests",
    "company_receipts",
    "financial_periods",
    "ledger_adjustments",
    "ledger_entries",
    "legacy_ledger_sessions",
    "manager_employee_assignments",
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
        # Mask credentials in output
        clean_url = database.DATABASE_URL.split("@")[-1] if "@" in database.DATABASE_URL else database.DATABASE_URL
        print(f"Host: {clean_url}")

    if not force:
        print("\nWARNING: This will permanently delete all users, requests, receipts, and audit events.")
        confirm = input("Type 'RESET' to confirm: ").strip()
        if confirm != "RESET":
            print("Aborted. No data was modified.")
            return

    with database.get_connection() as conn:
        cur = conn.cursor()

        if database.DATABASE_URL:
            # PostgreSQL: find which target tables actually exist in schema
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
            """)
            existing_tables = set(r["table_name"] for r in cur.fetchall())
            tables_to_truncate = [t for t in TARGET_TABLES if t in existing_tables]

            if tables_to_truncate:
                # Truncate all tables atomically in a single statement with CASCADE
                truncate_stmt = f"TRUNCATE TABLE {', '.join(tables_to_truncate)} CASCADE;"
                cur.execute(truncate_stmt)
                conn.commit()

                for t in tables_to_truncate:
                    print(f"  ✓ Cleared table: {t}")
            else:
                print("  No target tables found to clear.")
        else:
            # SQLite: temporarily disable FKs to avoid ordering constraints
            cur.execute("PRAGMA foreign_keys = OFF;")
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing_tables = set(r["name"] for r in cur.fetchall())

            for t in TARGET_TABLES:
                if t in existing_tables:
                    cur.execute(f"DELETE FROM {t};")
                    print(f"  ✓ Cleared table: {t}")

            conn.commit()
            cur.execute("PRAGMA foreign_keys = ON;")

        # Ensure base system roles, categories, and accounts remain populated
        database.seed_system_roles()
        database._seed_project_categories()
        conn.commit()

    # Clear in-memory cache
    clear_auth_cache()

    print("\nDatabase reset complete!")
    print("The system is now in a pristine state with 0 users.")
    print("Open the web app or run 'python scripts/create_admin.py' to initialize the first real administrator.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset PettyCash Pro database for production.")
    parser.add_argument("--force", action="store_true", help="Bypass confirmation prompt")
    args = parser.parse_args()
    reset_database(force=args.force)
