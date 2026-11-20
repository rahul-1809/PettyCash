"""Read-only export helpers for migrating legacy session data safely."""

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable


def iter_legacy_session_snapshots(
    list_sessions_fn: Callable[[], Iterable[Dict[str, Any]]],
    get_session_fn: Callable[[str], Dict[str, Any] | None],
) -> Iterable[Dict[str, Any]]:
    """Yield complete legacy sessions without mutating the source database."""
    for metadata in list_sessions_fn():
        session_id = str(metadata["id"])
        session = get_session_fn(session_id)
        if session is None:
            raise RuntimeError(f"Legacy session disappeared during export: {session_id}")
        yield session


def export_legacy_sessions(
    output_path: str | Path,
    list_sessions_fn: Callable[[], Iterable[Dict[str, Any]]],
    get_session_fn: Callable[[str], Dict[str, Any] | None],
) -> int:
    """Export legacy sessions to a JSON snapshot and return the session count."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sessions = list(iter_legacy_session_snapshots(list_sessions_fn, get_session_fn))
    destination.write_text(
        json.dumps({"format": "pettycash-legacy-session-v1", "sessions": sessions}, indent=2),
        encoding="utf-8",
    )
    return len(sessions)

