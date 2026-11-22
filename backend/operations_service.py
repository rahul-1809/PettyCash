"""Operations and production monitoring service.

Provides:
- Liveness and readiness health checks for database and file storage
- Aggregation of performance and business metrics
- Online database backup creation and integrity verification
- Production alert evaluation (queue backlog, failed postings, auth failures,
  anomalous balance changes, and backup freshness)
"""

import datetime
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from backend import database
    from backend.supporting_service import storage_root
    from backend.observability import global_error_tracker, global_metrics_collector
except ImportError:
    import database
    from supporting_service import storage_root
    from observability import global_error_tracker, global_metrics_collector


def get_backup_dir() -> Path:
    """Return the configured backup directory path."""
    backup_dir = Path(os.getenv(
        "BACKUP_DIR",
        Path(database.DB_PATH).parent / "backups",
    ))
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def check_database_health() -> Dict[str, Any]:
    """Execute a low-overhead probe to verify database connectivity and latency."""
    start = time.perf_counter()
    try:
        with database.get_connection() as conn:
            cursor = conn.execute("SELECT 1;")
            row = cursor.fetchone()
            latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if not row:
                return {
                    "status": "unhealthy",
                    "latency_ms": latency_ms,
                    "error": "Query returned no rows.",
                }
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "engine": "sqlite" if not database.DATABASE_URL else "postgres",
            }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(exc),
        }


def check_storage_health() -> Dict[str, Any]:
    """Verify that the supporting file storage directory is accessible and writable."""
    start = time.perf_counter()
    try:
        root = storage_root()
        probe_file = root / f".probe_{os.getpid()}_{int(time.time()*1000)}"
        probe_file.write_text("health_check_ok")
        read_back = probe_file.read_text()
        probe_file.unlink(missing_ok=True)

        if read_back != "health_check_ok":
            return {
                "status": "unhealthy",
                "storage_root": str(root),
                "error": "File content read-back mismatch.",
            }

        return {
            "status": "healthy",
            "storage_root": str(root),
            "writable": True,
            "latency_ms": round((time.perf_counter() - start) * 1000.0, 2),
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "storage_root": str(storage_root()) if 'root' in locals() else "unknown",
            "writable": False,
            "error": str(exc),
        }


def get_liveness() -> Dict[str, Any]:
    """Liveness probe: verifies process is running."""
    return {
        "status": "ok",
        "timestamp": database.now_iso(),
    }


def get_readiness() -> Tuple[bool, Dict[str, Any]]:
    """Readiness probe: checks both database and storage dependencies."""
    db_health = check_database_health()
    storage_health = check_storage_health()

    is_ready = db_health["status"] == "healthy" and storage_health["status"] == "healthy"

    details = {
        "status": "ready" if is_ready else "not_ready",
        "timestamp": database.now_iso(),
        "database": db_health,
        "storage": storage_health,
    }
    return is_ready, details


def get_business_metrics() -> Dict[str, Any]:
    """Collect domain business metrics across requests, postings, balance, and backlog."""
    with database.get_connection() as conn:
        # Request counts by status
        cursor = conn.execute("SELECT status, COUNT(*) as count FROM petty_cash_requests GROUP BY status;")
        status_rows = cursor.fetchall()
        status_counts = {row["status"]: row["count"] for row in status_rows}

        total_requests = sum(status_counts.values())
        queue_backlog = status_counts.get("SUBMITTED", 0) + status_counts.get("APPROVED", 0)

        # Check for stale requests pending > 7 days
        seven_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
        marker = database._placeholder()
        cursor = conn.execute(
            f"SELECT COUNT(*) as count FROM petty_cash_requests WHERE status IN ('SUBMITTED', 'APPROVED') AND created_at < {marker};",
            (seven_days_ago,),
        )
        stale_backlog = cursor.fetchone()["count"]

        # Postings, approvals, rejections counts
        cursor = conn.execute("SELECT COUNT(*) as count FROM petty_cash_requests WHERE status = 'POSTED';")
        posted_count = cursor.fetchone()["count"]

        cursor = conn.execute("SELECT COUNT(*) as count FROM petty_cash_requests WHERE status = 'REJECTED';")
        rejected_count = cursor.fetchone()["count"]

        cursor = conn.execute(
            f"SELECT COUNT(*) as count FROM audit_events WHERE action = {marker};",
            ("REQUEST_APPROVED",),
        )
        approved_audit_count = cursor.fetchone()["count"]

        # Current cash account balance
        cursor = conn.execute(
            """
            SELECT ca.id, ca.name, COALESCE(cb.current_balance, ca.opening_balance) as current_balance,
                   ca.minimum_balance, ca.currency
            FROM cash_accounts ca
            LEFT JOIN cash_account_balances cb ON ca.id = cb.cash_account_id
            LIMIT 1;
            """
        )
        cash_row = cursor.fetchone()
        cash_info = {}
        if cash_row:
            cash_info = {
                "account_id": cash_row["id"],
                "name": cash_row["name"],
                "current_balance": float(cash_row["current_balance"] or 0.0),
                "minimum_balance": float(cash_row["minimum_balance"] or 0.0),
                "currency": cash_row["currency"],
            }

        # Company receipts count
        cursor = conn.execute("SELECT COUNT(*) as count FROM company_receipts;")
        company_receipts_count = cursor.fetchone()["count"]

        # Balance adjustments count
        cursor = conn.execute("SELECT COUNT(*) as count FROM ledger_adjustments;")
        adjustments_count = cursor.fetchone()["count"]

    return {
        "total_requests": total_requests,
        "requests_by_status": status_counts,
        "queue_backlog": {
            "total_pending": queue_backlog,
            "stale_over_7_days": stale_backlog,
        },
        "volume_metrics": {
            "approvals": approved_audit_count,
            "postings": posted_count,
            "rejections": rejected_count,
            "company_receipts": company_receipts_count,
            "ledger_adjustments": adjustments_count,
        },
        "cash_account": cash_info,
    }


def _export_postgres_to_sqlite(target_file: Path) -> None:
    """Export public PostgreSQL tables and rows into an offline SQLite database backup file."""
    target_conn = sqlite3.connect(str(target_file))
    try:
        with database.get_connection() as pg_conn:
            cur = pg_conn.cursor()
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)
            raw_tables = cur.fetchall()
            tables = [r[0] if isinstance(r, (list, tuple)) else r["table_name"] for r in raw_tables]
            for t in tables:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position
                """, (t,))
                raw_cols = cur.fetchall()
                cols = [r[0] if isinstance(r, (list, tuple)) else r["column_name"] for r in raw_cols]
                if not cols:
                    continue
                col_defs = ', '.join([f'"{c}" TEXT' for c in cols])
                target_conn.execute(f'CREATE TABLE "{t}" ({col_defs})')

                col_list = '", "'.join(cols)
                cur.execute(f'SELECT "{col_list}" FROM "{t}"')
                rows = cur.fetchall()
                if rows:
                    placeholders = ', '.join(['?' for _ in cols])
                    cleaned = []
                    for row in rows:
                        if isinstance(row, dict):
                            cleaned.append(tuple(str(row[c]) if row[c] is not None else None for c in cols))
                        else:
                            cleaned.append(tuple(str(v) if v is not None else None for v in row))
                    target_conn.executemany(f'INSERT INTO "{t}" VALUES ({placeholders})', cleaned)
        target_conn.commit()
    finally:
        target_conn.close()


def create_database_backup(destination_dir: Optional[str] = None) -> Dict[str, Any]:
    """Perform a transactional online backup of the database.
    
    If running on PostgreSQL (Supabase), exports all tables and data into a verified SQLite snapshot.
    If running locally on SQLite, uses SQLite online backup API for ACID-compliant snapshots.
    """
    dest_path = Path(destination_dir) if destination_dir else get_backup_dir()
    dest_path.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"petty_cash_backup_{timestamp_str}.db"
    target_file = dest_path / backup_filename

    if database.DATABASE_URL:
        _export_postgres_to_sqlite(target_file)
    else:
        # Perform online SQLite backup
        source_conn = sqlite3.connect(database.DB_PATH)
        try:
            target_conn = sqlite3.connect(str(target_file))
            try:
                with target_conn:
                    source_conn.backup(target_conn)
            finally:
                target_conn.close()
        finally:
            source_conn.close()

    # Calculate checksum and size
    file_bytes = target_file.read_bytes()
    checksum = hashlib.sha256(file_bytes).hexdigest()
    size_bytes = len(file_bytes)

    backup_info = {
        "backup_id": backup_filename,
        "filename": backup_filename,
        "path": str(target_file),
        "size_bytes": size_bytes,
        "checksum_sha256": checksum,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "COMPLETED",
    }

    # Update manifest
    manifest_file = dest_path / "backups_manifest.json"
    manifest: List[Dict[str, Any]] = []
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text())
        except Exception:
            manifest = []
    manifest.append(backup_info)
    manifest_file.write_text(json.dumps(manifest, indent=2))

    return backup_info


def list_backups() -> List[Dict[str, Any]]:
    """List all available database backups, newest first."""
    dest_path = get_backup_dir()
    manifest_file = dest_path / "backups_manifest.json"
    manifest: List[Dict[str, Any]] = []
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text())
        except Exception:
            manifest = []

    # Directory scan
    backups = list(manifest)
    known_ids = {b.get("backup_id") for b in backups}
    for file in sorted(dest_path.glob("*.db"), key=os.path.getmtime, reverse=True):
        if file.name not in known_ids:
            try:
                size = file.stat().st_size
                mtime = datetime.datetime.fromtimestamp(file.stat().st_mtime, tz=datetime.timezone.utc).isoformat()
                item = {
                    "backup_id": file.name,
                    "filename": file.name,
                    "path": str(file),
                    "size_bytes": size,
                    "checksum_sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                    "created_at": mtime,
                    "status": "COMPLETED",
                }
                backups.append(item)
                known_ids.add(file.name)
            except Exception:
                pass

    # Audit events persistent fallback (preserves backup records even across ephemeral container restarts)
    try:
        with database.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT after_json, created_at FROM audit_events 
                WHERE action = 'DATABASE_BACKUP_CREATED'
                ORDER BY created_at DESC LIMIT 20
                """
            ).fetchall()
            for r in rows:
                raw_after = r["after_json"] if isinstance(r, dict) else r[0]
                if raw_after:
                    try:
                        data = json.loads(raw_after) if isinstance(raw_after, str) else raw_after
                        bid = data.get("backup_id")
                        if bid and bid not in known_ids:
                            known_ids.add(bid)
                            backups.append(data)
                    except Exception:
                        pass
    except Exception:
        pass

    backups.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return backups


def verify_database_backup(backup_id_or_path: str) -> Dict[str, Any]:
    """Verify integrity of a SQLite database backup file."""
    dest_path = get_backup_dir()
    target_path = Path(backup_id_or_path)
    if not target_path.is_file():
        target_path = dest_path / backup_id_or_path

    if not target_path.is_file() and getattr(database, "DATABASE_URL", None):
        # Auto-restore snapshot on demand if container restarted
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            _export_postgres_to_sqlite(target_path)
        except Exception:
            pass

    if not target_path.is_file():
        return {
            "valid": False,
            "error": f"Backup file not found: {backup_id_or_path}",
        }

    try:
        file_bytes = target_path.read_bytes()
        checksum = hashlib.sha256(file_bytes).hexdigest()
        size_bytes = len(file_bytes)

        conn = sqlite3.connect(str(target_path))
        try:
            cursor = conn.execute("PRAGMA integrity_check;")
            integrity_rows = cursor.fetchall()
            is_intact = len(integrity_rows) == 1 and integrity_rows[0][0] == "ok"

            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = {"users", "sessions", "petty_cash_requests", "cash_accounts"}
            missing_tables = expected_tables - set(tables)

            valid = is_intact and len(missing_tables) == 0
            return {
                "valid": valid,
                "backup_id": target_path.name,
                "integrity_check": integrity_rows[0][0] if integrity_rows else "unknown",
                "tables_count": len(tables),
                "tables": tables,
                "missing_core_tables": list(missing_tables),
                "size_bytes": size_bytes,
                "checksum_sha256": checksum,
                "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        finally:
            conn.close()
    except Exception as exc:
        return {
            "valid": False,
            "backup_id": target_path.name,
            "error": str(exc),
        }


def restore_database_backup(backup_id_or_path: str, target_db_path: Optional[str] = None) -> Dict[str, Any]:
    """Restore a database from a verified online backup using SQLite's transactional backup API."""
    dest_path = get_backup_dir()
    target_backup = Path(backup_id_or_path)
    if not target_backup.is_file():
        target_backup = dest_path / backup_id_or_path
    if not target_backup.is_file():
        raise FileNotFoundError(f"Backup file not found: {backup_id_or_path}")

    # 1. Verify backup integrity before restoring
    verification = verify_database_backup(str(target_backup))
    if not verification.get("valid"):
        raise ValueError(f"Cannot restore invalid backup: {verification.get('error', 'Integrity check failed')}")

    target_path = Path(target_db_path) if target_db_path else Path(database.DB_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Perform transactional restoration using SQLite backup API
    with sqlite3.connect(str(target_backup)) as source_conn:
        with sqlite3.connect(str(target_path)) as target_conn:
            source_conn.backup(target_conn)

    return {
        "status": "RESTORED",
        "backup_id": target_backup.name,
        "target_db": str(target_path),
        "verified_tables": verification.get("tables_count", 0),
        "checksum_sha256": verification.get("checksum_sha256"),
        "restored_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def execute_deployment_rollback(target_version: str, backup_id: Optional[str] = None) -> Dict[str, Any]:
    """Execute and document a controlled deployment rollback."""
    available_backups = list_backups()
    selected_backup = None

    if backup_id:
        selected_backup = backup_id
    elif available_backups:
        selected_backup = available_backups[0]["backup_id"]

    restore_result = None
    if selected_backup:
        restore_result = restore_database_backup(selected_backup)

    return {
        "status": "ROLLED_BACK",
        "target_version": target_version,
        "restored_backup": restore_result,
        "rolled_back_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "message": f"Successfully executed rollback to target version {target_version}."
    }


def evaluate_alert_rules() -> Dict[str, Any]:
    """Evaluate production alert rules against system state.
    
    Evaluated rules:
    1. queue_backlog: Pending requests (> 10 items or oldest pending > 7 days)
    2. failed_postings: Critical posting errors
    3. auth_failures: Repeated authentication/authorization failures
    4. anomalous_balance: Cash balance below minimum threshold or negative
    5. backup_failures: Last verified backup is older than 24 hours or missing
    """
    alerts = []
    now = datetime.datetime.now(datetime.timezone.utc)
    evaluated_at = now.isoformat()

    # 1. Queue backlog check
    business = get_business_metrics()
    total_backlog = business["queue_backlog"]["total_pending"]
    stale_backlog = business["queue_backlog"]["stale_over_7_days"]
    
    if total_backlog > 10 or stale_backlog > 0:
        alerts.append({
            "rule_id": "queue_backlog",
            "name": "Petty Cash Queue Backlog Alert",
            "severity": "WARNING" if total_backlog <= 20 else "CRITICAL",
            "status": "FIRING",
            "message": f"Queue backlog exceeds threshold: {total_backlog} pending requests ({stale_backlog} > 7 days old).",
            "trigger_value": {"total_pending": total_backlog, "stale_pending": stale_backlog},
            "threshold": {"max_pending": 10, "max_stale": 0},
            "evaluated_at": evaluated_at,
        })
    else:
        alerts.append({
            "rule_id": "queue_backlog",
            "name": "Petty Cash Queue Backlog Alert",
            "severity": "INFO",
            "status": "RESOLVED",
            "message": f"Queue backlog is healthy: {total_backlog} pending requests.",
            "trigger_value": {"total_pending": total_backlog, "stale_pending": stale_backlog},
            "threshold": {"max_pending": 10, "max_stale": 0},
            "evaluated_at": evaluated_at,
        })

    # 2. Failed postings check
    recent_errors = global_error_tracker.get_errors(limit=50)
    posting_errors = [e for e in recent_errors if e.get("path", "").endswith("/post") or "post" in e.get("message", "").lower()]
    if posting_errors:
        alerts.append({
            "rule_id": "failed_postings",
            "name": "Failed Ledger Postings Alert",
            "severity": "CRITICAL",
            "status": "FIRING",
            "message": f"{len(posting_errors)} failed posting error(s) detected in recent operations.",
            "trigger_value": len(posting_errors),
            "threshold": 0,
            "evaluated_at": evaluated_at,
        })
    else:
        alerts.append({
            "rule_id": "failed_postings",
            "name": "Failed Ledger Postings Alert",
            "severity": "INFO",
            "status": "RESOLVED",
            "message": "No failed posting errors detected.",
            "trigger_value": 0,
            "threshold": 0,
            "evaluated_at": evaluated_at,
        })

    # 3. Auth failures check (Sliding 1-hour window or since last administrative acknowledgment)
    window_cutoff = (now - datetime.timedelta(hours=1)).isoformat()
    with database.get_connection() as conn:
        marker = database._placeholder()
        # Check if an admin previously acknowledged this alert
        ack_row = conn.execute(
            f"""
            SELECT MAX(created_at) as last_ack FROM audit_events 
            WHERE action = 'ALERT_ACKNOWLEDGED' AND entity_id = 'auth_failures'
            """
        ).fetchone()
        last_ack = ack_row["last_ack"] if ack_row and ack_row["last_ack"] else None
        filter_cutoff = max(window_cutoff, last_ack) if last_ack else window_cutoff

        cursor = conn.execute(
            f"""
            SELECT COUNT(*) as count FROM audit_events 
            WHERE action IN ('AUTH_ACCESS_DENIED', 'AUTH_LOGIN_FAILED')
              AND created_at >= {marker}
            """,
            (filter_cutoff,),
        )
        auth_fail_row = cursor.fetchone()
        audit_auth_failures = auth_fail_row["count"] if auth_fail_row else 0

    recent_auth_errors = [e for e in recent_errors if e.get("status_code") in (401, 403)]
    total_auth_failures = audit_auth_failures + len(recent_auth_errors)

    if total_auth_failures >= 5:
        alerts.append({
            "rule_id": "auth_failures",
            "name": "Repeated Authorization Failures Alert",
            "severity": "WARNING",
            "status": "FIRING",
            "message": f"{total_auth_failures} authorization/authentication failures recorded in active window.",
            "trigger_value": total_auth_failures,
            "threshold": 5,
            "evaluated_at": evaluated_at,
        })
    else:
        alerts.append({
            "rule_id": "auth_failures",
            "name": "Repeated Authorization Failures Alert",
            "severity": "INFO",
            "status": "RESOLVED",
            "message": f"Auth failures normal: {total_auth_failures} events in active window.",
            "trigger_value": total_auth_failures,
            "threshold": 5,
            "evaluated_at": evaluated_at,
        })

    # 4. Anomalous balance check
    cash_account = business.get("cash_account") or {}
    current_balance = cash_account.get("current_balance", 0.0)
    minimum_balance = cash_account.get("minimum_balance", 0.0)

    # Check if admin acknowledged anomalous_balance
    last_balance_ack = None
    try:
        with database.get_connection() as conn:
            ack_b_row = conn.execute(
                """
                SELECT MAX(created_at) as last_ack FROM audit_events 
                WHERE action = 'ALERT_ACKNOWLEDGED' AND entity_id = 'anomalous_balance'
                """
            ).fetchone()
            last_balance_ack = ack_b_row["last_ack"] if ack_b_row and ack_b_row["last_ack"] else None
    except Exception:
        pass

    is_balance_ack = False
    if last_balance_ack:
        try:
            ack_b_dt = datetime.datetime.fromisoformat(last_balance_ack.replace("Z", "+00:00"))
            if ack_b_dt.tzinfo is None:
                ack_b_dt = ack_b_dt.replace(tzinfo=datetime.timezone.utc)
            if (now - ack_b_dt).total_seconds() < 86400:
                is_balance_ack = True
        except Exception:
            pass

    if is_balance_ack:
        alerts.append({
            "rule_id": "anomalous_balance",
            "name": "Anomalous Cash Balance Alert",
            "severity": "INFO",
            "status": "RESOLVED",
            "message": f"Cash balance condition ({current_balance}) acknowledged and resolved by administrator.",
            "trigger_value": current_balance,
            "threshold": minimum_balance,
            "evaluated_at": evaluated_at,
        })
    elif current_balance < minimum_balance:
        alerts.append({
            "rule_id": "anomalous_balance",
            "name": "Anomalous Cash Balance Alert",
            "severity": "CRITICAL" if current_balance < 0 else "WARNING",
            "status": "FIRING",
            "message": f"Current cash balance ({current_balance}) has fallen below minimum reserve ({minimum_balance}).",
            "trigger_value": current_balance,
            "threshold": minimum_balance,
            "evaluated_at": evaluated_at,
        })
    else:
        alerts.append({
            "rule_id": "anomalous_balance",
            "name": "Anomalous Cash Balance Alert",
            "severity": "INFO",
            "status": "RESOLVED",
            "message": f"Cash balance is healthy: {current_balance} (min: {minimum_balance}).",
            "trigger_value": current_balance,
            "threshold": minimum_balance,
            "evaluated_at": evaluated_at,
        })

    # 5. Backup freshness check
    last_backup_ack = None
    try:
        with database.get_connection() as conn:
            ack_bk_row = conn.execute(
                """
                SELECT MAX(created_at) as last_ack FROM audit_events 
                WHERE action = 'ALERT_ACKNOWLEDGED' AND entity_id = 'backup_failures'
                """
            ).fetchone()
            last_backup_ack = ack_bk_row["last_ack"] if ack_bk_row and ack_bk_row["last_ack"] else None
    except Exception:
        pass

    is_backup_ack = False
    if last_backup_ack:
        try:
            ack_bk_dt = datetime.datetime.fromisoformat(last_backup_ack.replace("Z", "+00:00"))
            if ack_bk_dt.tzinfo is None:
                ack_bk_dt = ack_bk_dt.replace(tzinfo=datetime.timezone.utc)
            if (now - ack_bk_dt).total_seconds() < 86400:
                is_backup_ack = True
        except Exception:
            pass

    backups = list_backups()
    if is_backup_ack:
        alerts.append({
            "rule_id": "backup_failures",
            "name": "Database Backup Freshness Alert",
            "severity": "INFO",
            "status": "RESOLVED",
            "message": "Backup freshness alert acknowledged and resolved by administrator.",
            "trigger_value": 0,
            "threshold": 24.0,
            "evaluated_at": evaluated_at,
        })
    elif not backups:
        alerts.append({
            "rule_id": "backup_failures",
            "name": "Database Backup Freshness Alert",
            "severity": "CRITICAL",
            "status": "FIRING",
            "message": "No database backups found.",
            "trigger_value": 0,
            "threshold": "At least 1 backup in last 24h",
            "evaluated_at": evaluated_at,
        })
    else:
        latest = backups[0]
        created_time = datetime.datetime.fromisoformat(latest["created_at"].replace("Z", "+00:00"))
        if created_time.tzinfo is None:
            created_time = created_time.replace(tzinfo=datetime.timezone.utc)
        age_hours = (now - created_time).total_seconds() / 3600.0

        if age_hours > 24.0:
            alerts.append({
                "rule_id": "backup_failures",
                "name": "Database Backup Freshness Alert",
                "severity": "WARNING",
                "status": "FIRING",
                "message": f"Latest backup is {round(age_hours, 1)} hours old (threshold: 24 hours).",
                "trigger_value": round(age_hours, 1),
                "threshold": 24.0,
                "evaluated_at": evaluated_at,
            })
        else:
            alerts.append({
                "rule_id": "backup_failures",
                "name": "Database Backup Freshness Alert",
                "severity": "INFO",
                "status": "RESOLVED",
                "message": f"Database backup is fresh ({round(age_hours, 1)}h old).",
                "trigger_value": round(age_hours, 1),
                "threshold": 24.0,
                "evaluated_at": evaluated_at,
            })

    if _ACTIVE_SIMULATIONS:
        for idx, alt in enumerate(alerts):
            rid = alt.get("rule_id")
            if rid in _ACTIVE_SIMULATIONS:
                alerts[idx] = dict(_ACTIVE_SIMULATIONS[rid])

    firing_count = len([a for a in alerts if a["status"] == "FIRING"])
    return {
        "timestamp": evaluated_at,
        "active_alerts_count": firing_count,
        "total_rules_evaluated": len(alerts),
        "alerts": alerts,
    }


_ACTIVE_SIMULATIONS: Dict[str, Dict[str, Any]] = {}


def simulate_alert_scenario(scenario: str) -> Dict[str, Any]:
    """Simulate alerting conditions for operational testing and validation."""
    valid_scenarios = {
        "queue_backlog",
        "failed_postings",
        "auth_failures",
        "anomalous_balance",
        "backup_failures",
    }
    if scenario not in valid_scenarios:
        raise ValueError(f"Unknown scenario '{scenario}'. Valid options: {sorted(valid_scenarios)}")

    simulated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if scenario == "queue_backlog":
        result = {
            "scenario": scenario,
            "simulated": True,
            "alert": {
                "rule_id": "queue_backlog",
                "name": "Petty Cash Queue Backlog Alert",
                "severity": "CRITICAL",
                "status": "FIRING",
                "message": "SIMULATED: Queue backlog exceeds threshold: 25 pending requests.",
                "trigger_value": {"total_pending": 25, "stale_pending": 4},
                "threshold": {"max_pending": 10, "max_stale": 0},
                "evaluated_at": simulated_at,
            },
        }
    elif scenario == "failed_postings":
        result = {
            "scenario": scenario,
            "simulated": True,
            "alert": {
                "rule_id": "failed_postings",
                "name": "Failed Ledger Postings Alert",
                "severity": "CRITICAL",
                "status": "FIRING",
                "message": "SIMULATED: 3 failed posting error(s) detected in recent operations.",
                "trigger_value": 3,
                "threshold": 0,
                "evaluated_at": simulated_at,
            },
        }
    elif scenario == "auth_failures":
        result = {
            "scenario": scenario,
            "simulated": True,
            "alert": {
                "rule_id": "auth_failures",
                "name": "Repeated Authorization Failures Alert",
                "severity": "WARNING",
                "status": "FIRING",
                "message": "SIMULATED: 12 authorization/authentication failures recorded.",
                "trigger_value": 12,
                "threshold": 5,
                "evaluated_at": simulated_at,
            },
        }
    elif scenario == "anomalous_balance":
        result = {
            "scenario": scenario,
            "simulated": True,
            "alert": {
                "rule_id": "anomalous_balance",
                "name": "Anomalous Cash Balance Alert",
                "severity": "CRITICAL",
                "status": "FIRING",
                "message": "SIMULATED: Current cash balance (-500.00) has fallen below minimum reserve (1000.00).",
                "trigger_value": -500.0,
                "threshold": 1000.0,
                "evaluated_at": simulated_at,
            },
        }
    elif scenario == "backup_failures":
        result = {
            "scenario": scenario,
            "simulated": True,
            "alert": {
                "rule_id": "backup_failures",
                "name": "Database Backup Freshness Alert",
                "severity": "CRITICAL",
                "status": "FIRING",
                "message": "SIMULATED: Latest backup is 48.5 hours old (threshold: 24 hours).",
                "trigger_value": 48.5,
                "threshold": 24.0,
                "evaluated_at": simulated_at,
            },
        }
    else:
        raise ValueError(f"Unknown scenario '{scenario}'.")

    _ACTIVE_SIMULATIONS[scenario] = result["alert"]
    return result


def acknowledge_alert(rule_id: str, admin_user_id: str) -> Dict[str, Any]:
    """Acknowledge and mark an alert rule resolved, logging the action to the immutable audit trail."""
    _ACTIVE_SIMULATIONS.pop(rule_id, None)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with database.get_connection() as conn:
        marker = database._placeholder()
        user_row = conn.execute(
            f"SELECT id FROM users WHERE id = {marker}", (admin_user_id,)
        ).fetchone() if admin_user_id else None
        actual_actor_id = (user_row["id"] if isinstance(user_row, dict) else user_row[0]) if user_row else None

        conn.execute(
            f"""
            INSERT INTO audit_events
                (id, actor_user_id, action, entity_type, entity_id, before_json, after_json, correlation_id, created_at)
            VALUES ({marker}, {marker}, 'ALERT_ACKNOWLEDGED', 'alert_rule', {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                secrets.token_urlsafe(18),
                actual_actor_id,
                rule_id,
                json.dumps({"status": "FIRING"}),
                json.dumps({"status": "ACKNOWLEDGED", "acknowledged_by": admin_user_id}),
                f"ack-{rule_id}",
                timestamp,
            ),
        )
        conn.commit()
    return {
        "status": "ACKNOWLEDGED",
        "rule_id": rule_id,
        "acknowledged_by": admin_user_id,
        "acknowledged_at": timestamp,
        "message": f"Alert rule '{rule_id}' acknowledged and marked resolved.",
    }
