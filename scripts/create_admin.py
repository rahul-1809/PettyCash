"""CLI script to bootstrap the first administrator in PettyCash Pro."""

import argparse
import sys
from pathlib import Path

# Add project root to Python module path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import database
from backend.user_service import create_bootstrap_admin


def main():
    parser = argparse.ArgumentParser(description="Create the initial bootstrap Admin user.")
    parser.add_argument("--username", required=True, help="Administrator username (e.g., Admin)")
    parser.add_argument("--email", required=True, help="Administrator email address")
    parser.add_argument("--password", required=True, help="Administrator password (min 12 chars)")
    args = parser.parse_args()

    try:
        user = create_bootstrap_admin(args.username, args.email, args.password)
        print("Successfully created initial Admin account:")
        print(f"  ID:       {user['id']}")
        print(f"  Username: {user['username']}")
        print(f"  Email:    {user['email']}")
        print(f"  Role:     {user['role']}")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
