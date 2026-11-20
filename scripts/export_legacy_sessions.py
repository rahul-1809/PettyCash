#!/usr/bin/env python3
"""Export existing session records without modifying the source database."""

import argparse
import sys
from pathlib import Path

# Allow direct execution from the repository root without requiring PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import get_session, list_sessions
from backend.legacy_migration import export_legacy_sessions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export legacy PettyCash sessions to a migration snapshot."
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="legacy-session-export.json",
        help="Destination JSON file (default: legacy-session-export.json)",
    )
    args = parser.parse_args()
    count = export_legacy_sessions(args.output, list_sessions, get_session)
    print(f"Exported {count} legacy session(s) to {args.output}")


if __name__ == "__main__":
    main()

