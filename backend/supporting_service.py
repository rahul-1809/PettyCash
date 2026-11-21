"""Private supporting-file storage and access control."""

import base64
import hashlib
import os
import re
import secrets
from pathlib import Path
from typing import Optional

try:
    from backend import database
    from backend.audit_service import record_audit_event
    from backend.notification_service import create_notification
except ImportError:
    import database
    from audit_service import record_audit_event
    from notification_service import create_notification


MAX_FILE_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")


def storage_root() -> Path:
    root = Path(os.environ.get(
        "SUPPORTING_FILES_DIR",
        Path(database.DB_PATH).parent / "private_supporting_files",
    ))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate_file(filename: str, content_type: str, content: bytes) -> str:
    name = Path(filename or "").name
    suffix = Path(name).suffix.lower()
    if not name or name != filename or ".." in name or not SAFE_FILENAME.fullmatch(name):
        raise ValueError("Filename is unsafe.")
    if suffix not in ALLOWED_TYPES:
        raise ValueError("Only PDF, PNG, and JPEG files are accepted.")
    if len(content) == 0:
        raise ValueError("Supporting file cannot be empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Supporting file exceeds the 10 MB limit.")
    expected_type = ALLOWED_TYPES[suffix]
    if content_type and content_type.lower() != expected_type:
        raise ValueError("File content type does not match its extension.")
    signatures = {
        "application/pdf": content.startswith(b"%PDF-"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
    }
    if not signatures[expected_type]:
        raise ValueError("File content could not be verified.")
    return name


def upload_supporting_file(
    request_id: str,
    uploader_id: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> dict:
    original_filename = _validate_file(filename, content_type, content)
    marker = database._placeholder()
    file_id = secrets.token_urlsafe(18)
    storage_key = f"{file_id}{Path(original_filename).suffix.lower()}"
    checksum = hashlib.sha256(content).hexdigest()
    path = storage_root() / storage_key

    with database.get_connection() as connection:
        request = connection.execute(
            f"""
            SELECT id, requester_id, status
            FROM petty_cash_requests WHERE id={marker}
            """,
            (request_id,),
        ).fetchone()
        if not request:
            raise LookupError("Request not found.")
        if request["requester_id"] != uploader_id:
            raise PermissionError("Only the requester can upload supporting files.")
        if request["status"] not in {"APPROVED", "SUPPORTING_UPLOADED"}:
            raise ValueError("Supporting files can only be uploaded after approval.")
        timestamp = database.now_iso()
        path.write_bytes(content)
        b64_content = base64.b64encode(content).decode("ascii")
        try:
            connection.execute(
                f"""
                INSERT INTO supporting_files
                    (id, request_id, storage_key, original_filename, content_type,
                     size_bytes, checksum_sha256, uploaded_by, created_at, file_data)
                VALUES ({marker}, {marker}, {marker}, {marker}, {marker},
                        {marker}, {marker}, {marker}, {marker}, {marker})
                """,
                (
                    file_id,
                    request_id,
                    storage_key,
                    original_filename,
                    ALLOWED_TYPES[Path(original_filename).suffix.lower()],
                    len(content),
                    checksum,
                    uploader_id,
                    timestamp,
                    b64_content,
                ),
            )
            if request["status"] == "APPROVED":
                connection.execute(
                    f"""
                    UPDATE petty_cash_requests
                    SET status='SUPPORTING_UPLOADED', updated_at={marker}
                    WHERE id={marker}
                    """,
                    (timestamp, request_id),
                )
                connection.execute(
                    f"""
                    INSERT INTO request_status_history
                        (id, request_id, from_status, to_status, changed_by, reason, created_at)
                    VALUES ({marker}, {marker}, 'APPROVED', 'SUPPORTING_UPLOADED',
                            {marker}, NULL, {marker})
                    """,
                    (secrets.token_urlsafe(18), request_id, uploader_id, timestamp),
                )
            connection.execute(
                f"""
                INSERT INTO audit_events
                    (id, actor_user_id, action, entity_type, entity_id,
                     before_json, after_json, correlation_id, created_at)
                VALUES ({marker}, {marker}, 'SUPPORTING_FILE_UPLOADED',
                        'petty_cash_request', {marker}, {marker}, {marker}, {marker}, {marker})
                """,
                (
                    secrets.token_urlsafe(18),
                    uploader_id,
                    request_id,
                    None,
                    '{"filename": "' + original_filename.replace('"', "") + '"}',
                    file_id,
                    timestamp,
                ),
            )
            connection.commit()
        except Exception:
            path.unlink(missing_ok=True)
            raise

    try:
        with database.get_connection() as conn:
            admins = conn.execute(
                "SELECT u.id FROM users u JOIN roles r ON r.id=u.role_id WHERE r.name='Admin' AND u.is_active=1"
            ).fetchall()
            emp = conn.execute(
                f"SELECT username FROM users WHERE id={database._placeholder()}",
                (uploader_id,),
            ).fetchone()
            req_info = conn.execute(
                f"SELECT amount, purpose FROM petty_cash_requests WHERE id={database._placeholder()}",
                (request_id,),
            ).fetchone()
        emp_name = emp["username"] if emp else "Employee"
        amt_str = f"₹{req_info['amount']}" if req_info else ""
        purpose_str = req_info["purpose"] if req_info else "Petty cash request"
        for adm in admins:
            create_notification(
                adm["id"],
                "REQUEST_READY_FOR_POSTING",
                f"Voucher uploaded by {emp_name}",
                f"Request for {amt_str} ({purpose_str}) by {emp_name} has supporting voucher '{original_filename}' attached and is ready for posting.",
                "petty_cash_request",
                request_id,
            )
    except Exception:
        pass

    return {
        "id": file_id,
        "request_id": request_id,
        "original_filename": original_filename,
        "content_type": ALLOWED_TYPES[Path(original_filename).suffix.lower()],
        "size_bytes": len(content),
        "checksum_sha256": checksum,
    }


def list_supporting_files(request_id: str) -> list[dict]:
    marker = database._placeholder()
    with database.get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT id, request_id, original_filename, content_type, size_bytes,
                   checksum_sha256, uploaded_by, created_at
            FROM supporting_files WHERE request_id={marker}
            ORDER BY created_at ASC
            """,
            (request_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_supporting_file(
    file_id: str,
    requester_id: Optional[str] = None,
    role: Optional[str] = None,
) -> tuple[dict, Path]:
    marker = database._placeholder()
    with database.get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT f.*, r.requester_id, r.status AS request_status
            FROM supporting_files f
            JOIN petty_cash_requests r ON r.id=f.request_id
            WHERE f.id={marker}
            """,
            (file_id,),
        ).fetchone()
    if not row:
        raise LookupError("Supporting file not found.")

    # Access control:
    # 1. Admin can access any file.
    # 2. Requester can access their own file.
    # 3. For public/report hyperlinks (e.g. clicked from downloaded Excel report):
    #    allow access if the request is in an approved or posted state (audit evidence).
    is_admin = (role == "Admin")
    is_owner = (requester_id is not None and row["requester_id"] == requester_id)
    is_posted_or_approved = (row["request_status"] in ("POSTED", "APPROVED", "SUPPORTING_UPLOADED"))

    if not is_admin and not is_owner:
        if not is_posted_or_approved:
            raise PermissionError("You cannot access this supporting file.")

    path = storage_root() / row["storage_key"]
    if not path.is_file():
        file_bytes = None
        if row.get("file_data"):
            try:
                file_bytes = base64.b64decode(row["file_data"])
            except Exception:
                file_bytes = None

        if not file_bytes:
            with database.get_connection() as conn:
                f_row = conn.execute(
                    f"SELECT file_data FROM supporting_files WHERE id={marker}",
                    (file_id,),
                ).fetchone()
                if f_row and f_row.get("file_data"):
                    try:
                        file_bytes = base64.b64decode(f_row["file_data"])
                    except Exception:
                        file_bytes = None

        if file_bytes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(file_bytes)
        else:
            raise FileNotFoundError("Supporting file is unavailable.")
    record_audit_event(
        actor_user_id=requester_id,
        action="SUPPORTING_FILE_DOWNLOADED",
        entity_type="supporting_file",
        entity_id=file_id,
        after={
            "filename": row["original_filename"],
            "request_id": row["request_id"],
            "source": "DIRECT_DOWNLOAD" if requester_id else "REPORT_AUDIT_LINK",
        },
        correlation_id=file_id,
    )
    return dict(row), path
